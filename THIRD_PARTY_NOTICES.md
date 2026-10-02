# Third-Party Notices

This file tracks planned and bundled third-party software. Entries marked as
"planned" are not bundled yet.

| Name | Status | License | Source |
|---|---|---|---|
| MeanVC2 | planned integration | Apache-2.0 | https://github.com/ASLP-lab/MeanVC2 |
| RVC | planned integration | MIT | https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI |
| ONNX Runtime | planned integration | MIT | https://github.com/microsoft/onnxruntime |
| Qt | planned runtime dependency | LGPL-3.0 / GPL / commercial | https://www.qt.io/licensing/open-source-lgpl-obligations |
| DeepFilterNet | bundled runtime and model checkpoint | Apache-2.0 OR MIT | https://github.com/Rikorose/DeepFilterNet |
| FCPE | planned integration | Verify upstream license before bundling | https://github.com/CNChTu/FCPE |
| Vocos | planned model component | MIT | https://github.com/gemelo-ai/vocos |
| nlohmann/json | bundled source dependency | MIT | https://github.com/nlohmann/json |

Before the first binary release:

1. Pin every dependency version.
2. Copy the exact upstream license text into `third_party/notices`.
3. Record whether the component is dynamically linked, statically linked, or
   distributed as a separate process.
4. Add source offer or relinking information if required by the upstream
   license.
5. Regenerate this file as part of the release process.

DeepFilterNet's upstream license notice is included in
`third_party/notices/deepfilternet-LICENSE` and is copied into packaged builds.

