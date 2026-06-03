(function () {
  "use strict";

  var PHRASE = "delete";

  function initDeleteAccountModal() {
    var modalEl = document.getElementById("deleteAccountModal");
    var form = document.getElementById("deleteAccountForm");
    if (!modalEl || !form) {
      return;
    }

    var phraseInput = document.getElementById("deletePhraseInput");
    var confirmPhrase = document.getElementById("confirm_phrase");
    var continueBtn = document.getElementById("deleteAccountContinue");
    var submitBtn = document.getElementById("deleteAccountSubmit");
    var backBtn = document.getElementById("deleteAccountBack");
    var emailInput = document.getElementById("confirm_email");
    var passwordInput = document.getElementById("password");
    var step1 = modalEl.querySelector('[data-delete-step="1"]');
    var step2 = modalEl.querySelector('[data-delete-step="2"]');
    var modalTitle = document.getElementById("deleteAccountModalTitle");
    var modalDesc = document.getElementById("deleteAccountModalDesc");

    if (!phraseInput || !continueBtn || !submitBtn || !step1 || !step2) {
      return;
    }

    function phraseMatches() {
      return phraseInput.value.trim().toLowerCase() === PHRASE;
    }

    function updatePhraseState() {
      var ok = phraseMatches();
      continueBtn.disabled = !ok;
      phraseInput.classList.toggle("is-valid", ok);
      phraseInput.classList.toggle("is-invalid", phraseInput.value.length > 0 && !ok);
    }

    function showStep(step) {
      var onStep2 = step === 2;
      step1.classList.toggle("d-none", onStep2);
      step2.classList.toggle("d-none", !onStep2);
      continueBtn.classList.toggle("d-none", onStep2);
      submitBtn.classList.toggle("d-none", !onStep2);
      if (modalTitle) {
        modalTitle.textContent = onStep2 ? "Confirm your identity" : "Delete your account?";
      }
      if (modalDesc) {
        modalDesc.textContent = onStep2
          ? "Verify your credentials to complete deletion."
          : "This action cannot be undone.";
      }
      if (onStep2 && emailInput) {
        emailInput.focus();
      } else if (phraseInput) {
        phraseInput.focus();
      }
    }

    function resetModal() {
      phraseInput.value = "";
      phraseInput.classList.remove("is-valid", "is-invalid");
      if (confirmPhrase) {
        confirmPhrase.value = "";
      }
      if (emailInput) {
        emailInput.value = "";
      }
      if (passwordInput) {
        passwordInput.value = "";
      }
      continueBtn.disabled = true;
      showStep(1);
    }

    phraseInput.addEventListener("input", updatePhraseState);

    phraseInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter" && phraseMatches()) {
        event.preventDefault();
        continueBtn.click();
      }
    });

    continueBtn.addEventListener("click", function () {
      if (!phraseMatches()) {
        return;
      }
      if (confirmPhrase) {
        confirmPhrase.value = PHRASE;
      }
      showStep(2);
    });

    if (backBtn) {
      backBtn.addEventListener("click", function () {
        if (confirmPhrase) {
          confirmPhrase.value = "";
        }
        showStep(1);
        updatePhraseState();
      });
    }

    modalEl.addEventListener("hidden.bs.modal", resetModal);

    modalEl.addEventListener("shown.bs.modal", function () {
      resetModal();
      phraseInput.focus();
    });

    form.addEventListener("submit", function (event) {
      if (confirmPhrase && confirmPhrase.value.trim().toLowerCase() !== PHRASE) {
        event.preventDefault();
        showStep(1);
        updatePhraseState();
        return;
      }
      if (!emailInput || !passwordInput) {
        event.preventDefault();
        return;
      }
      var email = emailInput.value.trim().toLowerCase();
      var password = passwordInput.value;
      if (!email || !password) {
        event.preventDefault();
        if (!email) {
          emailInput.classList.add("is-invalid");
          emailInput.focus();
        }
        if (!password) {
          passwordInput.classList.add("is-invalid");
          if (email) {
            passwordInput.focus();
          }
        }
      }
    });

    if (emailInput) {
      emailInput.addEventListener("input", function () {
        emailInput.classList.remove("is-invalid");
      });
    }
    if (passwordInput) {
      passwordInput.addEventListener("input", function () {
        passwordInput.classList.remove("is-invalid");
      });
    }
  }

  document.addEventListener("DOMContentLoaded", initDeleteAccountModal);
})();
