const { API_URL, COGNITO_REGION, COGNITO_CLIENT_ID } = window.APP_CONFIG;
const $ = (id) => document.getElementById(id);

let token = sessionStorage.getItem("idToken");

/* ---------- helpers ---------- */
function setMessage(text, kind = "") {
  const el = $("message");
  el.textContent = text;
  el.className = kind;
}

function formatSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showView() {
  $("auth-view").hidden = !!token;
  $("app-view").hidden = !token;
}

/* ---------- Cognito (called directly over HTTPS, no SDK needed) ---------- */
async function cognito(target, payload) {
  const res = await fetch(`https://cognito-idp.${COGNITO_REGION}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-amz-json-1.1",
      "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}`,
    },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || data.__type || "Request failed");
  return data;
}

async function signUp() {
  await cognito("SignUp", {
    ClientId: COGNITO_CLIENT_ID,
    Username: $("email").value.trim(),
    Password: $("password").value,
    UserAttributes: [{ Name: "email", Value: $("email").value.trim() }],
  });
  $("confirm-box").hidden = false;
  setMessage("Account created. Enter the verification code sent to your email.", "ok");
}

async function confirmSignUp() {
  await cognito("ConfirmSignUp", {
    ClientId: COGNITO_CLIENT_ID,
    Username: $("email").value.trim(),
    ConfirmationCode: $("code").value.trim(),
  });
  $("confirm-box").hidden = true;
  setMessage("Account confirmed. You can log in now.", "ok");
}

async function login() {
  const data = await cognito("InitiateAuth", {
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: COGNITO_CLIENT_ID,
    AuthParameters: { USERNAME: $("email").value.trim(), PASSWORD: $("password").value },
  });
  token = data.AuthenticationResult.IdToken;
  sessionStorage.setItem("idToken", token);
  $("password").value = "";
  setMessage("");
  showView();
  await loadFiles();
}

function logout() {
  token = null;
  sessionStorage.removeItem("idToken");
  $("file-list").replaceChildren();
  showView();
}

/* ---------- API calls ---------- */
async function api(path, options = {}) {
  const res = await fetch(API_URL + path, {
    ...options,
    headers: { "Content-Type": "application/json", Authorization: token, ...(options.headers || {}) },
  });
  if (res.status === 401) {
    logout();
    throw new Error("Session expired. Please log in again.");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.message || "Request failed");
  return data;
}

async function loadFiles() {
  const files = await api("/files");
  const tbody = $("file-list");
  tbody.replaceChildren();

  if (files.length === 0) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.textContent = "No files yet. Upload your first file above.";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  for (const f of files) {
    const tr = document.createElement("tr");

    const name = document.createElement("td");
    name.textContent = f.file_name; // textContent => safe from HTML injection
    const size = document.createElement("td");
    size.textContent = formatSize(Number(f.size));
    const date = document.createElement("td");
    date.textContent = new Date(f.uploaded_at).toLocaleString();

    const actions = document.createElement("td");
    actions.className = "actions";

    const dl = document.createElement("button");
    dl.textContent = "Download";
    dl.addEventListener("click", () => run(() => downloadFile(f.file_id)));

    const del = document.createElement("button");
    del.textContent = "Delete";
    del.className = "danger";
    del.addEventListener("click", () => run(() => deleteFile(f.file_id, f.file_name)));

    actions.append(dl, del);
    tr.append(name, size, date, actions);
    tbody.appendChild(tr);
  }
}

async function uploadFile() {
  const file = $("file-input").files[0];
  if (!file) throw new Error("Choose a file first.");

  setMessage("Uploading...");
  const { upload_url } = await api("/upload-url", {
    method: "POST",
    body: JSON.stringify({ file_name: file.name, content_type: file.type, size: file.size }),
  });

  // The file goes straight to S3 (it never passes through Lambda).
  const put = await fetch(upload_url, {
    method: "PUT",
    headers: { "Content-Type": file.type },
    body: file,
  });
  if (!put.ok) throw new Error("Upload to storage failed.");

  $("file-input").value = "";
  setMessage("Upload complete.", "ok");
  await loadFiles();
}

async function downloadFile(fileId) {
  const { download_url } = await api(`/files/${fileId}`);
  window.location.href = download_url;
}

async function deleteFile(fileId, name) {
  if (!confirm(`Delete "${name}"?`)) return;
  await api(`/files/${fileId}`, { method: "DELETE" });
  setMessage("File deleted.", "ok");
  await loadFiles();
}

/* Run an action and show any error in the message bar. */
async function run(fn) {
  try {
    await fn();
  } catch (err) {
    setMessage(err.message, "error");
  }
}

/* ---------- wire up ---------- */
$("signup-btn").addEventListener("click", () => run(signUp));
$("confirm-btn").addEventListener("click", () => run(confirmSignUp));
$("login-btn").addEventListener("click", () => run(login));
$("logout-btn").addEventListener("click", logout);
$("upload-btn").addEventListener("click", () => run(uploadFile));

showView();
if (token) run(loadFiles);
