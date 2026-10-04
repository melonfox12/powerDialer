export const ParticlesMixin = (Base) => class extends Base {
  resizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(window.innerWidth * ratio);
    this.canvas.height = Math.round(window.innerHeight * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  burstParticles() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const colors = ["#e1b76d", "#4cc38a", "#dfff78", "#fff1bd"];
    const originX = window.innerWidth / 2;
    const originY = window.innerHeight / 2;
    this.particles = Array.from({ length: 72 }, () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = 1.5 + Math.random() * 5;
      return {
        x: originX, y: originY,
        vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 45 + Math.random() * 35, size: 2 + Math.random() * 3,
        color: colors[Math.floor(Math.random() * colors.length)],
      };
    });
    if (!this.particleFrame) this.particleFrame = requestAnimationFrame(() => this.drawParticles());
  }

  drawParticles() {
    this.particleFrame = 0;
    this.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    this.particles = this.particles.filter((particle) => particle.life > 0);
    for (const particle of this.particles) {
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += 0.035;
      particle.life -= 1;
      this.context.globalAlpha = Math.min(1, particle.life / 20);
      this.context.fillStyle = particle.color;
      this.context.fillRect(particle.x, particle.y, particle.size, particle.size);
    }
    this.context.globalAlpha = 1;
    if (this.particles.length) this.particleFrame = requestAnimationFrame(() => this.drawParticles());
  }

  stopParticles() {
    if (this.particleFrame) cancelAnimationFrame(this.particleFrame);
    this.particleFrame = 0;
    this.particles = [];
    this.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
  }
};
