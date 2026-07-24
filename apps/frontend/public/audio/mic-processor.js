// AudioWorklet de captura de mic para la llamada en vivo. Corre en el
// AudioContext creado a sampleRate 16000 (ver useLiveVoiceCall.ts) — el
// navegador resamplea la captura real del hardware a esa tasa, así que acá
// solo convierte Float32 [-1,1] a PCM16LE y lo manda al hilo principal.
class MicProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (channel && channel.length) {
      const pcm16 = new Int16Array(channel.length)
      for (let i = 0; i < channel.length; i += 1) {
        const sample = Math.max(-1, Math.min(1, channel[i]))
        pcm16[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff
      }
      this.port.postMessage(pcm16.buffer, [pcm16.buffer])
    }
    return true
  }
}

registerProcessor('mic-processor', MicProcessor)
