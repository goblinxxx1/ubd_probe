import axios from "axios";

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE || "/api",
});

let unauthorizedHandler = null;
export function setUnauthorizedHandler(fn) {
  unauthorizedHandler = fn;
}

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("ubd_admin_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const isLoginRequest = error?.config?.url?.endsWith("/auth/login");
    if (error?.response?.status === 401 && unauthorizedHandler && !isLoginRequest) {
      unauthorizedHandler();
    }
    return Promise.reject(error);
  }
);

export default client;
