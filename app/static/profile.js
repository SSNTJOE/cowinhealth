const profileMsg = document.getElementById("profile-msg");

async function loadProfile() {
  const data = await api("/api/me?include_email=true");
  if (!data.logged_in) {
    window.location.href = "/";
    return;
  }
  const user = data.user;
  document.getElementById("anon-id").textContent = user.user_id;
  document.getElementById("email").value = user.email || "";
  document.getElementById("nickname").value = user.nickname || "";
  document.getElementById("birth_year").value = user.birth_year || "";
  document.getElementById("gender").value = user.gender || "";
}

document.getElementById("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  profileMsg.textContent = "";
  try {
    await api("/api/profile", {
      method: "POST",
      body: formBody({
        nickname: document.getElementById("nickname").value,
        birth_year: document.getElementById("birth_year").value,
        gender: document.getElementById("gender").value,
      }),
    });
    profileMsg.textContent = "已儲存";
    profileMsg.className = "status ok";
    window.location.href = "/";
  } catch (err) {
    profileMsg.textContent = formatApiError(err);
    profileMsg.className = "status err";
  }
});

loadProfile().catch((err) => {
  profileMsg.textContent = formatApiError(err);
  profileMsg.className = "status err";
});
