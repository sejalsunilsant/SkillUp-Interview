function showLogin() {
  document.getElementById("login-box").classList.remove("hidden");
  document.getElementById("register-box").classList.add("hidden");
  document.getElementById("msg").textContent = "";
}

function showRegister() {
  document.getElementById("register-box").classList.remove("hidden");
  document.getElementById("login-box").classList.add("hidden");
  document.getElementById("msg").textContent = "";
}

async function login() {
  const email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;
  const msg = document.getElementById("msg");

  if (!email || !password) {
    msg.textContent = "Email and password are required";
    msg.className = "error";
    return;
  }

  const res = await fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password })
  });

  const data = await res.json();

  if (res.ok) {
    window.location.href = "/interview";
  } else {
    msg.textContent = data.error;
    msg.className = "error";
  }
}

function register() {
  const name = document.getElementById("reg-name").value.trim();
  const email = document.getElementById("reg-email").value.trim();
  const password = document.getElementById("reg-password").value;
  const confirm = document.getElementById("reg-confirm").value;
  const msg = document.getElementById("msg");

  if (!name || !email || !password || !confirm) {
    msg.textContent = "All fields are required";
    msg.className = "error";
    return;
  }

  if (password !== confirm) {
    msg.textContent = "Passwords do not match";
    msg.className = "error";
    return;
  }

  fetch("/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, email, password })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      msg.textContent = "Registration successful! Please login.";
      msg.className = "success";
      showLogin();
    } else {
      msg.textContent = data.message;
      msg.className = "error";
    }
  });
}
