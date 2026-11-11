"""Create a 48 kHz fake-microphone WAV from the Live output saved by ws_smoke."""
from array import array
from pathlib import Path
import sys
import wave


def main():
    source = Path("tmp/live-answer.wav")
    destination = Path("tmp/live-input.wav")
    with wave.open(str(source), "rb") as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise SystemExit("Expected mono 16-bit PCM WAV")
        rate = audio.getframerate()
        samples = array("h")
        samples.frombytes(audio.readframes(audio.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    target_rate = 48000
    output = array("h")
    for index in range(round(len(samples) * target_rate / rate)):
        position = index * rate / target_rate
        left = min(int(position), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        mix = position - left
        output.append(round(samples[left] * (1 - mix) + samples[right] * mix))
    if sys.byteorder != "little":
        output.byteswap()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(destination), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(target_rate)
        audio.writeframes(bytes(target_rate * 2) + output.tobytes() + bytes(target_rate * 2 * 5))
    print(destination)


if __name__ == "__main__":
    main()
