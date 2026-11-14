// Shared helper: calls the API on the same site and turns errors into
// the Arabic message the server sent.
const GENERIC_ERROR = "حدث خطأ، حاول مرة أخرى";
const NETWORK_ERROR = "تعذر الاتصال بالخادم، تحقق من الإنترنت وحاول مرة أخرى";

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function api(method, path, body) {
  const options = { method, headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, options);
  } catch (e) {
    throw new ApiError(0, NETWORK_ERROR);
  }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty body */ }
  if (!res.ok) {
    const detail = data && typeof data.detail === "string" ? data.detail : GENERIC_ERROR;
    throw new ApiError(res.status, detail);
  }
  return data;
}

// For doctor pages: if not logged in, go to the login page.
function handleDoctorError(err, showMessage) {
  if (err.status === 401) {
    window.location.href = "/login.html";
    return;
  }
  showMessage(err.message);
}

function showError(el, text) {
  el.textContent = text;
  el.className = "msg error";
}

function clearMsg(el) {
  el.textContent = "";
  el.className = "msg";
}
