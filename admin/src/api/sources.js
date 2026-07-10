import client from "./client";

export const list = () => client.get("/admin/sources").then((r) => r.data);
export const create = (payload) => client.post("/admin/sources", payload).then((r) => r.data);
export const update = (id, payload) => client.patch(`/admin/sources/${id}`, payload).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/sources/${id}`).then((r) => r.data);
