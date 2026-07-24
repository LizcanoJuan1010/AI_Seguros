// AudioWorklet de reproducción para el audio TTS de Deepgram (PCM16LE, el
// AudioContext de playback se crea a sampleRate 24000 en useLiveVoiceCall.ts).
// Cola simple de chunks Float32; `{cmd:'clear'}` vacía la cola de inmediato
// — es lo que usa el barge-in para cortar la voz de la IA sin esperar a que
// termine el buffer en curso.
class PcmPlayerProcessor extends AudioWorkletProcessor {
  constructor() {
    super()
    this.queue = []
    this.readOffset = 0
    this.port.onmessage = (event) => {
      if (event.data?.cmd === 'clear') {
        this.queue = []
        this.readOffset = 0
        return
      }
      const int16 = new Int16Array(event.data)
      const float32 = new Float32Array(int16.length)
      for (let i = 0; i < int16.length; i += 1) {
        const s = int16[i]
        float32[i] = s < 0 ? s / 0x8000 : s / 0x7fff
      }
      this.queue.push(float32)
    }
  }

  process(_inputs, outputs) {
    const output = outputs[0][0]
    let outIdx = 0
    while (outIdx < output.length) {
      if (this.queue.length === 0) {
        output.fill(0, outIdx)
        break
      }
      const current = this.queue[0]
      const remaining = current.length - this.readOffset
      const toCopy = Math.min(remaining, output.length - outIdx)
      output.set(current.subarray(this.readOffset, this.readOffset + toCopy), outIdx)
      outIdx += toCopy
      this.readOffset += toCopy
      if (this.readOffset >= current.length) {
        this.queue.shift()
        this.readOffset = 0
      }
    }
    return true
  }
}

registerProcessor('pcm-player-processor', PcmPlayerProcessor)
