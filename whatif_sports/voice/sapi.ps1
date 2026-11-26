# Offline TTS with the built-in Windows voices (System.Speech). Called by voice/tts.py.
param(
    [Parameter(Mandatory = $true)][string]$TextFile,
    [Parameter(Mandatory = $true)][string]$OutFile,
    [string]$Voice = "",
    [int]$Rate = 1
)
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    if ($Voice) { $synth.SelectVoice($Voice) }
    $synth.Rate = $Rate
    $synth.SetOutputToWaveFile($OutFile)
    $synth.Speak([System.IO.File]::ReadAllText($TextFile))
}
finally {
    $synth.Dispose()
}
