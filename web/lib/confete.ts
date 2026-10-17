/* Confetes de parabéns (empresa com tudo "bateu"). Curto, sem biblioteca, respeita "reduzir movimento". */
const CORES = ["#ff6a00", "#ff9538", "#2159c9", "#157347", "#f2c14e"];

export function confete(origem?: Element | null): void {
  try {
    if (typeof window === "undefined" || !document.body.animate) return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    const r = origem?.getBoundingClientRect();
    const x0 = r ? r.left + r.width / 2 : window.innerWidth / 2;
    const y0 = r ? r.top + r.height / 2 : window.innerHeight / 3;
    const caixa = document.createElement("div");
    caixa.setAttribute("aria-hidden", "true");
    caixa.style.cssText = "position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:9999";
    document.body.appendChild(caixa);
    for (let i = 0; i < 44; i++) {
      const p = document.createElement("i");
      const w = 6 + Math.random() * 6;
      p.style.cssText = `position:absolute;display:block;left:${x0}px;top:${y0}px;width:${w}px;height:${w * 0.5}px;border-radius:2px;background:${CORES[i % CORES.length]}`;
      caixa.appendChild(p);
      const ang = -Math.PI / 2 + (Math.random() - 0.5) * Math.PI * 0.9;
      const vel = 160 + Math.random() * 260;
      const dx = Math.cos(ang) * vel, dy = Math.sin(ang) * vel;
      const queda = 300 + Math.random() * 240;
      const giro = (Math.random() - 0.5) * 900;
      p.animate([
        { transform: "translate(0,0) rotate(0deg)", opacity: 1, offset: 0 },
        { transform: `translate(${dx * 0.6}px,${dy * 0.6}px) rotate(${giro * 0.5}deg)`, opacity: 1, offset: 0.35 },
        { transform: `translate(${dx}px,${dy + queda}px) rotate(${giro}deg)`, opacity: 0, offset: 1 },
      ], { duration: 2600 + Math.random() * 400, easing: "cubic-bezier(.2,.7,.4,1)", fill: "forwards" });
    }
    setTimeout(() => caixa.remove(), 3200);
  } catch {
    /* enfeite: nunca atrapalha o trabalho */
  }
}
