export function resizeCanvas(arcade) {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    arcade.canvas.width = Math.round(window.innerWidth * ratio);
    arcade.canvas.height = Math.round(window.innerHeight * ratio);
    arcade.context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

export function burstParticles(arcade) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const colors = ["#e1b76d", "#4cc38a", "#dfff78", "#fff1bd"];
    const originX = window.innerWidth / 2;
    const originY = window.innerHeight / 2;
    arcade.particles = Array.from({ length: 72 }, () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = 1.5 + Math.random() * 5;
      return {
        x: originX, y: originY,
        vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 45 + Math.random() * 35, size: 2 + Math.random() * 3,
        color: colors[Math.floor(Math.random() * colors.length)],
      };
    });
    if (!arcade.particleFrame) arcade.particleFrame = requestAnimationFrame(() => arcade.drawParticles());
  }

export function drawParticles(arcade) {
    arcade.particleFrame = 0;
    arcade.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    arcade.particles = arcade.particles.filter((particle) => particle.life > 0);
    for (const particle of arcade.particles) {
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += 0.035;
      particle.life -= 1;
      arcade.context.globalAlpha = Math.min(1, particle.life / 20);
      arcade.context.fillStyle = particle.color;
      arcade.context.fillRect(particle.x, particle.y, particle.size, particle.size);
    }
    arcade.context.globalAlpha = 1;
    if (arcade.particles.length) arcade.particleFrame = requestAnimationFrame(() => arcade.drawParticles());
  }

export function stopParticles(arcade) {
    if (arcade.particleFrame) cancelAnimationFrame(arcade.particleFrame);
    arcade.particleFrame = 0;
    arcade.particles = [];
    arcade.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
  }
