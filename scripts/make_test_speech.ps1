[CmdletBinding()]
param(
    [string]$Output = "",
    [string]$VoiceName = "",
    [string]$Text = "",
    [switch]$ListVoices
)

# Generates real speech for verification. `panda voice-check` needs actual
# speech: speaker embeddings of a pure tone are meaningless, which is exactly
# how the original tone-based fixture was found to be useless.
#
# Windows ships the voices, so this needs no network and no extra dependency.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer

try {
    if ($ListVoices -or [string]::IsNullOrWhiteSpace($VoiceName)) {
        $synth.GetInstalledVoices() |
            Where-Object { $_.Enabled } |
            ForEach-Object {
                Write-Host (
                    "voice: {0} | {1} | {2}" -f `
                        $_.VoiceInfo.Name,
                        $_.VoiceInfo.Culture,
                        $_.VoiceInfo.Gender
                )
            }
    }

    if (-not [string]::IsNullOrWhiteSpace($Output)) {
        if ([string]::IsNullOrWhiteSpace($VoiceName)) {
            throw "-VoiceName is required when writing a file"
        }
        if ([string]::IsNullOrWhiteSpace($Text)) {
            throw "-Text is required when writing a file"
        }

        $synth.SelectVoice($VoiceName)

        # 16 kHz mono 16-bit: what the engine consumes.
        $format = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(
            16000,
            [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,
            [System.Speech.AudioFormat.AudioChannel]::Mono
        )
        $synth.SetOutputToWaveFile($Output, $format)
        $synth.Speak($Text)
        $synth.SetOutputToNull()
        Write-Host "wrote $Output"
    }
}
finally {
    $synth.Dispose()
}
