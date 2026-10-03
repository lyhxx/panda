from __future__ import annotations

import unittest

from panda_infer import onnx_export

HAVE_ONNX = onnx_export.onnx is not None


def _have_torch() -> bool:
    try:
        import torch  # noqa: F401
    except ImportError:
        return False
    return True


HAVE_TORCH = _have_torch()


class AsrVariantTest(unittest.TestCase):
    def test_variants_mirror_the_upstream_runtime(self) -> None:
        # These values must match MODEL_PATHS in MeanVC2's run_rt.py; a drift
        # here would export a graph whose cache shapes do not fit the stream.
        self.assertEqual(set(onnx_export.ASR_VARIANTS), {"40ms", "120ms"})
        self.assertEqual(onnx_export.ASR_VARIANTS["40ms"]["bn_window"], 11)
        self.assertEqual(
            onnx_export.ASR_VARIANTS["40ms"]["required_cache_size"],
            4,
        )
        self.assertEqual(onnx_export.ASR_VARIANTS["40ms"]["offset_init"], 4)
        self.assertEqual(onnx_export.ASR_VARIANTS["120ms"]["bn_window"], 19)
        self.assertEqual(
            onnx_export.ASR_VARIANTS["120ms"]["required_cache_size"],
            8,
        )
        self.assertEqual(onnx_export.ASR_VARIANTS["120ms"]["offset_init"], 8)


@unittest.skipUnless(HAVE_TORCH, "ASR inputs need torch")
class AsrInputsTest(unittest.TestCase):
    def test_shapes_follow_the_variant(self) -> None:
        inputs = onnx_export.asr_inputs("40ms")
        self.assertEqual(tuple(inputs["fbank"].shape), (1, 11, 80))
        self.assertEqual(tuple(inputs["att_cache"].shape), (6, 4, 4, 128))
        self.assertEqual(tuple(inputs["cnn_cache"].shape), (6, 1, 256, 8))

        wide = onnx_export.asr_inputs("120ms")
        self.assertEqual(tuple(wide["fbank"].shape), (1, 19, 80))
        self.assertEqual(tuple(wide["att_cache"].shape), (6, 4, 8, 128))
        self.assertEqual(int(wide["offset"]), 8)

    def test_unknown_variant_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            onnx_export.asr_inputs("nope")


@unittest.skipUnless(HAVE_ONNX, "ONNX export needs the onnx package")
class PatchScatterIndicesTest(unittest.TestCase):
    def build_model(self, nodes):
        helper = onnx_export.helper
        TensorProto = onnx_export.TensorProto
        graph = helper.make_graph(
            nodes,
            "probe",
            [helper.make_tensor_value_info("a", TensorProto.FLOAT, [2])],
            [helper.make_tensor_value_info("d", TensorProto.FLOAT, [2])],
        )
        return helper.make_model(graph)

    def test_inserts_a_cast_before_each_scatter(self) -> None:
        helper = onnx_export.helper
        model = self.build_model(
            [helper.make_node("ScatterND", ["a", "indices"], ["d"])]
        )

        patched = onnx_export.patch_scatter_indices(model)

        self.assertEqual(patched, 1)
        self.assertEqual(
            [node.op_type for node in model.graph.node],
            ["Cast", "ScatterND"],
        )
        cast = model.graph.node[0]
        self.assertEqual(list(cast.input), ["indices"])
        self.assertEqual(cast.output[0], "indices_as_int64")
        self.assertEqual(cast.attribute[0].i, onnx_export.TensorProto.INT64)
        self.assertEqual(model.graph.node[1].input[1], "indices_as_int64")

    def test_is_idempotent(self) -> None:
        helper = onnx_export.helper
        model = self.build_model(
            [helper.make_node("ScatterND", ["a", "indices"], ["d"])]
        )

        onnx_export.patch_scatter_indices(model)
        again = onnx_export.patch_scatter_indices(model)

        self.assertEqual(again, 0)
        self.assertEqual(len(model.graph.node), 2)

    def test_leaves_other_nodes_alone(self) -> None:
        helper = onnx_export.helper
        model = self.build_model([helper.make_node("Relu", ["a"], ["d"])])

        patched = onnx_export.patch_scatter_indices(model)

        self.assertEqual(patched, 0)
        self.assertEqual(
            [node.op_type for node in model.graph.node],
            ["Relu"],
        )

    def test_keeps_topological_order_with_several_scatters(self) -> None:
        helper = onnx_export.helper
        model = self.build_model(
            [
                helper.make_node("ScatterND", ["a", "i1"], ["b"]),
                helper.make_node("Relu", ["b"], ["c"]),
                helper.make_node("ScatterND", ["c", "i2"], ["d"]),
            ]
        )

        patched = onnx_export.patch_scatter_indices(model)

        self.assertEqual(patched, 2)
        self.assertEqual(
            [node.op_type for node in model.graph.node],
            ["Cast", "ScatterND", "Relu", "Cast", "ScatterND"],
        )
        # Each cast sits immediately before its consumer, so no node is moved
        # ahead of something it depends on.
        self.assertEqual(model.graph.node[1].input[1], "i1_as_int64")
        self.assertEqual(model.graph.node[4].input[1], "i2_as_int64")


if __name__ == "__main__":
    unittest.main()
