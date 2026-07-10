import client from "./client";

export const list = () => client.get("/admin/users").then((r) => r.data);
export const create = (payload) => client.post("/admin/users", payload).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/users/${id}`).then((r) => r.data);
