/* Login page behavior: tab switching between Windows/AD and local demo
   login, plus the two sign-in flows themselves. */

(function () {
  const tabWindows = document.getElementById("pms-tab-windows");
  const tabDemo = document.getElementById("pms-tab-demo");
  const panelWindows = document.getElementById("pms-panel-windows");
  const panelDemo = document.getElementById("pms-panel-demo");
  const errorBox = document.getElementById("pms-login-error");
  const continueWindowsBtn = document.getElementById("pms-continue-windows");
  const demoForm = document.getElementById("pms-panel-demo");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("pms-hide");
  }

  function hideError() {
    errorBox.classList.add("pms-hide");
  }

  function selectTab(which) {
    hideError();
    if (which === "windows") {
      tabWindows.classList.add("active");
      tabDemo.classList.remove("active");
      panelWindows.classList.remove("pms-hide");
      panelDemo.classList.add("pms-hide");
    } else {
      tabDemo.classList.add("active");
      tabWindows.classList.remove("active");
      panelDemo.classList.remove("pms-hide");
      panelWindows.classList.add("pms-hide");
    }
  }

  tabWindows.addEventListener("click", () => selectTab("windows"));
  tabDemo.addEventListener("click", () => selectTab("demo"));

  // Windows/AD flow: IIS (or the dev server, if AUTH_MODE=iis_forwarded /
  // ldap_bind is configured) resolves identity ahead of the app, so this
  // just probes whether a session already exists / can be established via
  // the browser's own Windows-auth negotiation on the reverse proxy.
  continueWindowsBtn.addEventListener("click", async () => {
    hideError();
    continueWindowsBtn.disabled = true;
    continueWindowsBtn.textContent = "Checking session...";
    try {
      await PMS.me();
      location.href = "dashboard.html";
    } catch (err) {
      showError(
        err.status === 401
          ? "No authenticated Windows session was found. Make sure this app is reached through the configured reverse proxy with Windows Integrated Authentication enabled."
          : (err.message || "Could not verify your Windows session.")
      );
    } finally {
      continueWindowsBtn.disabled = false;
      continueWindowsBtn.textContent = "Continue with Windows account";
    }
  });

  // Local demo login flow: posts credentials to /auth/login, which (when
  // AUTH_MODE=demo_local) checks them against the Demo_Login table.
  demoForm.addEventListener("submit", async (evt) => {
    evt.preventDefault();
    hideError();
    const username = document.getElementById("pms-user").value.trim();
    const password = document.getElementById("pms-pass").value;
    if (!username || !password) {
      showError("Enter a username and password.");
      return;
    }
    const submitBtn = demoForm.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Signing in...";
    try {
      await PMS.post("/auth/login", { username, password });
      location.href = "dashboard.html";
    } catch (err) {
      showError(err.message || "Sign in failed. Check your username and password.");
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Sign in";
    }
  });

  // If a session already exists (e.g. user navigated back to login.html
  // manually after signing in), skip straight to the dashboard.
  PMS.me().then(() => { location.href = "dashboard.html"; }).catch(() => {});
})();
