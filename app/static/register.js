const mysqlStatus = document.getElementById("mysql-status");
const authMsg = document.getElementById("auth-msg");

async function checkMysql() {
  try {
    const data = await api("/api/health");
    mysqlStatus.textContent = data.mysql ? "MySQL 連線成功" : "MySQL 回應異常";
    mysqlStatus.className = data.mysql ? "status ok" : "status err";
  } catch (err) {
    mysqlStatus.textContent = "MySQL 尚未連上：" + err.message;
    mysqlStatus.className = "status err";
  }
}

document.getElementById("register-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  authMsg.textContent = "";
  try {
    const data = await api("/api/register", {
      method: "POST",
      body: formBody({
        email: document.getElementById("email").value,
        password: document.getElementById("password").value,
      }),
    });
    authMsg.textContent = "已建立匿名 ID：" + data.user_id;
    authMsg.className = "status ok";
    sessionStorage.removeItem("daily-asked");
    window.location.href = "/profile";
  } catch (err) {
    authMsg.textContent = err.message;
    authMsg.className = "status err";
  }
});

checkMysql();
