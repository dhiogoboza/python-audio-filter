#!python

import sys
import wave
import pyaudio
import wavfile
import argparse
import numpy as np

from playsound import playsound
from scipy.signal import kaiserord, lfilter, firwin, freqz
from pylab import figure, plot, xlabel, ylabel, xlim, ylim, title, grid, axes, show

OUTPUT_FOLDER = 'out/'

CHUNK = 1024
CHANNELS = 1
NOISE_A = 500

class Noiser:
  """
  Utiliy class to generate a noise.
  Core extracted from https://stackoverflow.com/questions/33933842/how-to-generate-noise-in-frequency-range-with-numpy
  """
  def __init__(self):
    pass

  def fftnoise(self, f):
    f = np.array(f, dtype="complex")
    Np = (len(f) - 1) // 2
    phases = np.random.rand(Np) * 2 * np.pi
    phases = np.cos(phases) + 1j * np.sin(phases)
    f[1 : Np + 1] *= phases
    f[-1 : -1 - Np : -1] = np.conj(f[1 : Np + 1])
    return np.fft.ifft(f).real

  def band_limited_noise(self, min_freq, max_freq, samples=1024, samplerate=1):
    freqs = np.abs(np.fft.fftfreq(samples, 1 / samplerate))
    f = np.zeros(samples)
    f[np.logical_and(freqs >= min_freq, freqs <= max_freq)] = 1
    return self.fftnoise(f)

class Recorder:
  def __init__(self, duration, sample_rate):
    self.duration = duration
    self.sample_rate = sample_rate

  def __do_record(self, chunk, channels, files_prefix, aformat=pyaudio.paInt16):
    p = pyaudio.PyAudio()
    stream = p.open(format=aformat, channels=channels, rate=self.sample_rate, input=True, frames_per_buffer=chunk)

    print("* recording")
    frames = []
    for i in range(0, int(self.sample_rate / chunk * self.duration)):
      data = stream.read(chunk)
      frames.append(data)
    print("* done recording")

    stream.stop_stream()
    stream.close()
    p.terminate()

    file_output = OUTPUT_FOLDER + files_prefix + "_output.wav"
    wf = wave.open(file_output, 'wb')
    wf.setnchannels(channels)
    wf.setsampwidth(p.get_sample_size(aformat))
    wf.setframerate(self.sample_rate)
    wf.writeframes(b''.join(frames))
    wf.close()

    return file_output

  def record(self, files_prefix):
    return self.__do_record(CHUNK, CHANNELS, files_prefix)

class KaiserFilter:
  def __init__(self, sample_rate, cutoff_hz_1, cutoff_hz_2, ripple_db):
    self.sample_rate = sample_rate
    self.cutoff_hz_1 = cutoff_hz_1
    self.cutoff_hz_2 = cutoff_hz_2
    self.ripple_db = ripple_db

  def add_noise_and_filter(self, x, noise, play_sounds, files_prefix):
    t = np.arange(len(x)) / self.sample_rate

    # Plot original signal.
    figure()
    plot(t, x)
    title('Original signal')
    grid(True)

    #------------------------------------------------
    # Add noise to original signal
    #------------------------------------------------
    with_noise = x + noise

    # Plot the signal with noise.
    figure()
    plot(t, with_noise)
    title('Signal with noise')
    grid(True)

    # Save audio with noise.
    output_with_noise = ''.join([OUTPUT_FOLDER, files_prefix, '_with_noise.wav'])
    wavfile.write(output_with_noise, self.sample_rate, with_noise, normalized=True)

    # Override x signal.
    x = with_noise

    #------------------------------------------------
    # Create a FIR filter and apply it to x.
    #------------------------------------------------

    # The Nyquist rate of the signal.
    nyq_rate = self.sample_rate / 2.0

    # The desired width of the transition from pass to stop,
    # relative to the Nyquist rate.
    width = (self.cutoff_hz_2 - self.cutoff_hz_1) / nyq_rate

    # Compute the order and Kaiser parameter for the FIR filter.
    N, beta = kaiserord(self.ripple_db, width)
    N |= 1

    # Use firwin with a Kaiser window to create a lowpass FIR filter.
    taps = firwin(N, [self.cutoff_hz_1 / nyq_rate, self.cutoff_hz_2 / nyq_rate], window=('kaiser', beta), pass_zero=True)

    # Use lfilter to filter x with the FIR filter.
    filtered_x = lfilter(taps, 1.0, x)

    #------------------------------------------------
    # Plot the magnitude response of the filter.
    #------------------------------------------------

    figure()
    w, h = freqz(taps, worN=8000)
    plot((w / np.pi) * nyq_rate, np.absolute(h))
    xlabel('Frequency (Hz)')
    ylabel('Gain')
    title('Frequency response')
    ylim(-0.05, 1.05)
    grid(True)

    #------------------------------------------------
    # Plot the filtered signal.
    #------------------------------------------------

    # The phase delay of the filtered signal.
    delay = 0.5 * (N - 1) / self.sample_rate

    # Plot the filtered signal, shifted to compensate for the phase delay.
    figure()
    # Plot just the "good" part of the filtered signal.  The first N-1
    # samples are "corrupted" by the initial conditions.
    plot(t[N-1:]-delay, filtered_x[N-1:], 'g')

    title('Filtered signal')
    xlabel('t')
    grid(True)

    # Save filtered audio
    output_filtered = "".join([OUTPUT_FOLDER, files_prefix, '_filtered.wav'])
    wavfile.write(output_filtered, self.sample_rate, filtered_x, normalized=True)

    if play_sounds:
      playsound(output_with_noise)
      playsound(output_filtered)

    # Show plotted figures
    show()

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('--duration', '-d', default=5, type=int, help='Recording duration in seconds')
  parser.add_argument('--rate', '-r', default=44100, type=int, help='Audio sample rate')
  parser.add_argument('--window', '-w', choices=['kaiser'], default='kaiser', help='Filter window type')
  parser.add_argument('--cutoffhz1', '-wc1', default=1900, type=int, help='The cutoff frequency 1 of the filter')
  parser.add_argument('--cutoffhz2', '-wc2', default=2100, type=int, help='The cutoff frequency 2 of the filter')
  parser.add_argument('--ripple_db', '-rd', default=60, type=int, help='The desired attenuation in the stop band, in dB')
  parser.add_argument('--noise_1', '-n1', default=1950, type=int, help='Noise minimum frequency')
  parser.add_argument('--noise_2', '-n2', default=2050, type=int, help='Noise maximum frequency')
  parser.add_argument('--play', '-p', default=True, type=bool, help='Play audios with and without noise')

  args = vars(parser.parse_args())

  files_prefix = '_'.join(['noise', str(args['noise_1']), str(args['noise_2'])\
      , str(args['cutoffhz1']), str(args['cutoffhz2']), str(args['ripple_db'])])

  audio_path = Recorder(args['duration'], args['rate']).record(files_prefix)
  x = wavfile.read(audio_path, normalized=True, forcestereo=False)[1]
  noise = Noiser().band_limited_noise(min_freq=args['noise_1'], max_freq=args['noise_2']\
      , samples=len(x), samplerate=args['rate']) * NOISE_A

  if args['window'] == 'kaiser':
    KaiserFilter(args['rate'], args['cutoffhz1'], args['cutoffhz2'], args['ripple_db'])\
        .add_noise_and_filter(x, noise, args['play'], files_prefix)

if __name__ == "__main__":
  main()