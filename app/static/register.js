const mysqlStatus = document.getElementById("mysql-status");
const authMsg = document.getElementById("auth-msg");
const captcha = bindCaptchaControls();

async function checkMysql() {
  try {
    const data = await api("/api/health");
    mysqlStatus.textContent = data.mysql ? uiText("mysqlOk") : uiText("mysqlBad");
    mysqlStatus.className = data.mysql ? "status ok" : "status err";
  } catch (err) {
    mysqlStatus.textContent = uiText("mysqlOffline") + formatApiError(err);
    mysqlStatus.className = "status err";
  }
}

document.getElementById("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  authMsg.textContent = "";
  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value;
  const validEmail = /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email);
  if (!validEmail || password.length < 6) {
    authMsg.textContent = uiText("registerNeedFields");
    authMsg.className = "status err";
    return;
  }
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: formBody({
        email,
        password,
        ...authCaptchaFields(),
      }),
    });
    try {
      await api("/api/profile", {
        method: "POST",
        body: formBody({ preferred_lang: getUiLang() }),
      });
    } catch (_err) { /* profile may be incomplete; lang still local */ }
    authMsg.textContent = uiText("registerOkPrefix") + data.user_id;
    authMsg.className = "status ok";
    sessionStorage.removeItem("daily-asked");
    window.location.href = "/profile";
  } catch (err) {
    authMsg.textContent = formatApiError(err);
    authMsg.className = "status err";
    captcha.reload();
  }
});

bindUiLang(() => checkMysql());
checkMysql();
