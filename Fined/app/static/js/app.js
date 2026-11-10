(() => {
  document.documentElement.classList.replace("no-js", "js");

  const isoLocal = (data) => {
    const m = String(data.getMonth() + 1).padStart(2, "0");
    const d = String(data.getDate()).padStart(2, "0");
    return `${data.getFullYear()}-${m}-${d}`;
  };

  const fecharToast = (toast) => toast?.remove();

  document.querySelectorAll(".toast").forEach((toast, i) => {
    setTimeout(() => fecharToast(toast), 5200 + i * 600);
  });

  document.addEventListener("click", (evento) => {
    const fechar = evento.target.closest("[data-fechar-toast]");
    if (fechar) fecharToast(fechar.closest(".toast"));
  });

  const dialogo = document.getElementById("confirmar");
  let formPendente = null;

  document.addEventListener("submit", (evento) => {
    const form = evento.target;
    if (!form.matches("[data-confirmar]") || form.dataset.confirmado === "1") return;
    if (!dialogo || typeof dialogo.showModal !== "function") {
      if (!window.confirm(form.dataset.confirmar || "Confirmar exclusão")) evento.preventDefault();
      return;
    }
    evento.preventDefault();
    formPendente = form;
    dialogo.querySelector("[data-confirmar-texto]").textContent = form.dataset.confirmar || "";
    dialogo.querySelector("#confirmar-titulo").textContent = form.dataset.confirmarTitulo || "Confirmar exclusão";
    dialogo.querySelector("[data-confirmar-sim]").textContent = form.dataset.confirmarBotao || "Excluir";
    dialogo.returnValue = "";
    dialogo.showModal();
  });

  if (dialogo) {
    dialogo.addEventListener("close", () => {
      if (dialogo.returnValue === "sim" && formPendente) {
        formPendente.dataset.confirmado = "1";
        formPendente.submit();
      }
      formPendente = null;
    });
    dialogo.addEventListener("click", (evento) => {
      if (evento.target === dialogo) dialogo.close("nao");
    });
  }

  document.querySelectorAll(".form-lanc").forEach((form) => {
    const aplicar = () => {
      const marcado = form.querySelector('input[name="tipo"]:checked');
      const tipo = marcado ? marcado.value : "despesa";
      form.querySelectorAll("[data-categorias]").forEach((grupo) => {
        const ativo = grupo.dataset.categorias === tipo;
        grupo.toggleAttribute("data-inativo", !ativo);
        grupo.querySelector("select").disabled = !ativo;
      });
    };
    form.addEventListener("change", (evento) => {
      if (evento.target.name === "tipo") aplicar();
    });
    aplicar();
  });

  document.querySelectorAll("[data-dia]").forEach((botao) => {
    botao.addEventListener("click", () => {
      const alvo = document.getElementById(botao.dataset.alvo);
      if (!alvo) return;
      const data = new Date();
      data.setDate(data.getDate() - Number(botao.dataset.dia || 0));
      alvo.value = isoLocal(data);
      alvo.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });

  document.querySelectorAll("[data-valor-rapido]").forEach((botao) => {
    botao.addEventListener("click", () => {
      const alvo = document.getElementById(botao.dataset.alvo);
      if (!alvo) return;
      alvo.value = botao.dataset.valorRapido;
      alvo.focus();
    });
  });

  document.querySelectorAll("[data-olho]").forEach((botao) => {
    botao.addEventListener("click", () => {
      const campo = document.getElementById(botao.dataset.olho);
      if (!campo) return;
      const mostrar = campo.type === "password";
      campo.type = mostrar ? "text" : "password";
      botao.setAttribute("aria-pressed", String(mostrar));
      botao.setAttribute("aria-label", mostrar ? "Esconder senha" : "Mostrar senha");
    });
  });

})();

