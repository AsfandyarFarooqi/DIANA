/* DIANA voice I/O — mic capture with silence auto-stop, Whisper transcription, JARVIS-style playback. */
const Voice = (() => {
  let ctx = null;
  let player = null;
  let session = 0;

  function audioCtx() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
    return ctx;
  }

  function rmsSampler(analyser) {
    const buf = new Uint8Array(analyser.fftSize);
    return () => {
      analyser.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) {
        const x = (buf[i] - 128) / 128;
        sum += x * x;
      }
      return Math.sqrt(sum / buf.length);
    };
  }

  // ---------- input ----------
  const recorderType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg']
    .find(t => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || '';
  const canRecord = !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);

  async function record({ onLevel = () => {}, silenceMs = 1300, noSpeechMs = 8000, maxMs = 60000 } = {}) {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    const ac = audioCtx();
    const source = ac.createMediaStreamSource(stream);
    const analyser = ac.createAnalyser();
    analyser.fftSize = 1024;
    source.connect(analyser);
    const sample = rmsSampler(analyser);

    const rec = new MediaRecorder(stream, recorderType ? { mimeType: recorderType } : undefined);
    const chunks = [];
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };

    const started = performance.now();
    let heard = false, forced = false, quietSince = 0, noise = 0.01, timer = null;

    const done = new Promise(resolve => {
      rec.onstop = () => {
        clearInterval(timer);
        source.disconnect();
        stream.getTracks().forEach(t => t.stop());
        onLevel(0);
        const type = rec.mimeType || recorderType || 'audio/webm';
        resolve((heard || forced) && chunks.length ? new Blob(chunks, { type }) : null);
      };
    });

    const stop = (manual = false) => {
      forced = forced || manual;
      if (rec.state !== 'inactive') rec.stop();
    };

    // ~12 samples/s is plenty for voice activity detection and the level meter.
    timer = setInterval(() => {
      const level = sample();
      const now = performance.now();
      onLevel(Math.min(1, level * 6));
      if (!heard) noise = noise * 0.9 + Math.min(level, 0.05) * 0.1;
      if (level > Math.max(0.02, noise * 2.5)) {
        heard = true;
        quietSince = 0;
      } else if (heard) {
        quietSince = quietSince || now;
        if (now - quietSince > silenceMs) stop();
      }
      if ((!heard && now - started > noSpeechMs) || now - started > maxMs) stop();
    }, 80);

    rec.start(250);
    return { stop, done };
  }

  async function transcribe(blob, name) {
    const ext = /mp4/.test(blob.type) ? 'mp4' : /ogg/.test(blob.type) ? 'ogg' : 'webm';
    const form = new FormData();
    form.append('audio', blob, name || `speech.${ext}`);
    const res = await fetch('/api/transcribe', { method: 'POST', body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `Transcription failed (${res.status})`);
    return data.text || '';
  }

  // ---------- output ----------
  function buildPlayer() {
    const ac = audioCtx();
    const el = new Audio();
    el.preload = 'auto';
    const src = ac.createMediaElementSource(el);
    // Subtle synthetic colour: trim lows, lift presence, even out dynamics, faint 14 ms doubling.
    const highpass = ac.createBiquadFilter();
    highpass.type = 'highpass';
    highpass.frequency.value = 110;
    const presence = ac.createBiquadFilter();
    presence.type = 'peaking';
    presence.frequency.value = 3200;
    presence.Q.value = 0.9;
    presence.gain.value = 3.5;
    const comp = ac.createDynamicsCompressor();
    comp.threshold.value = -20;
    comp.ratio.value = 3;
    const delay = ac.createDelay(0.05);
    delay.delayTime.value = 0.014;
    const wet = ac.createGain();
    wet.gain.value = 0.16;
    const analyser = ac.createAnalyser();
    analyser.fftSize = 512;

    src.connect(highpass).connect(presence).connect(comp);
    comp.connect(ac.destination);
    comp.connect(delay).connect(wet).connect(ac.destination);
    comp.connect(analyser);
    return { el, sample: rmsSampler(analyser) };
  }

  function pickBrowserVoice(urdu) {
    const voices = speechSynthesis.getVoices();
    if (urdu) return voices.find(v => /^ur/i.test(v.lang)) || null;
    const prefs = [/Ryan/i, /George/i, /UK English Male/i, /Daniel/i];
    for (const p of prefs) {
      const v = voices.find(v => p.test(v.name) && /^en/i.test(v.lang));
      if (v) return v;
    }
    return voices.find(v => /^en-GB/i.test(v.lang)) || voices.find(v => /^en/i.test(v.lang)) || null;
  }

  function browserSpeak(text, id, onStart, onEnd) {
    if (!window.speechSynthesis) return onEnd();
    const urdu = /[؀-ۿ]/.test(text);
    const u = new SpeechSynthesisUtterance(text.replace(/```[\s\S]*?```/g, '').replace(/[*_`#>]/g, ''));
    u.lang = urdu ? 'ur-PK' : 'en-GB';
    u.voice = pickBrowserVoice(urdu);
    u.pitch = urdu ? 1 : 0.85;
    u.rate = 1.03;
    u.onstart = () => { if (id === session) onStart(); };
    u.onend = u.onerror = onEnd;
    speechSynthesis.speak(u);
  }

  function speak(text, { onStart = () => {}, onEnd = () => {}, onLevel = () => {} } = {}) {
    stop();
    const id = ++session;
    const clean = text.slice(0, 2500);
    let timer = null, finished = false, fellBack = false;

    const finish = () => {
      if (finished || id !== session) return;
      finished = true;
      clearInterval(timer);
      onLevel(0);
      onEnd();
    };

    player = player || buildPlayer();
    const { el, sample } = player;
    el.onplaying = () => {
      if (id !== session) return;
      onStart();
      clearInterval(timer);
      timer = setInterval(() => onLevel(Math.min(1, sample() * 5)), 80);
    };
    el.onended = finish;
    el.onerror = () => {
      if (id !== session || fellBack) return;
      fellBack = true;
      clearInterval(timer);
      browserSpeak(clean, id, onStart, finish);
    };
    el.src = `/api/tts?text=${encodeURIComponent(clean)}`;
    el.play().catch(err => { if (err.name === 'NotAllowedError') finish(); });
  }

  function stop() {
    session++;
    if (player) {
      const { el } = player;
      el.onplaying = el.onended = el.onerror = null;
      el.pause();
      el.removeAttribute('src');
      el.load();
    }
    if (window.speechSynthesis) speechSynthesis.cancel();
  }

  if (window.speechSynthesis) speechSynthesis.getVoices(); // warm the voice list

  return { canRecord, record, transcribe, speak, stop, unlock: audioCtx };
})();
