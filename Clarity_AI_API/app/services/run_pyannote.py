import sys
import json
import soundfile as sf
import torch

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "Missing arguments"}))
        sys.exit(1)

    file_path = sys.argv[1]
    token = sys.argv[2]

    try:
        from pyannote.audio import Pipeline

        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
        pipeline.to(device)

        speech, sr = sf.read(file_path)
        if speech.ndim == 1:
            waveform = torch.from_numpy(speech).float().unsqueeze(0)
        else:
            waveform = torch.from_numpy(speech.T).float()

        if sr != 16000:
            import torchaudio.transforms as T
            resampler = T.Resample(sr, 16000)
            waveform = resampler(waveform)
            sr = 16000

        audio_dict = {"waveform": waveform, "sample_rate": sr}
        diarization = pipeline(audio_dict)

        turns = []
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            turns.append({"start": turn.start, "end": turn.end, "speaker": speaker})

        print("PYANNOTE_JSON_START")
        print(json.dumps({"turns": turns}))
        print("PYANNOTE_JSON_END")
    except Exception as exc:
        print("PYANNOTE_JSON_START")
        print(json.dumps({"error": str(exc)}))
        print("PYANNOTE_JSON_END")

if __name__ == "__main__":
    main()
