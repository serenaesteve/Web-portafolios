document.addEventListener("DOMContentLoaded", () => {
    const links = document.querySelectorAll('a[href^="#"]');

    links.forEach(link => {
        link.addEventListener("click", function (e) {
            const targetId = this.getAttribute("href");
            if (targetId.length > 1) {
                const target = document.querySelector(targetId);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({ behavior: "smooth" });
                }
            }
        });
    });

    const chips = document.querySelectorAll(".prompt-chip");
    const promptInput = document.querySelector("#prompt");

    chips.forEach(chip => {
        chip.addEventListener("click", () => {
            if (promptInput) {
                promptInput.value = chip.textContent.trim();
                promptInput.focus();
            }
        });
    });

    const reveals = document.querySelectorAll(".reveal");

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add("visible");
            }
        });
    }, { threshold: 0.15 });

    reveals.forEach(el => observer.observe(el));
});
