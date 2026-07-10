import client from "./client";

export const list = (params) => client.get("/admin/offers", { params }).then((r) => r.data);
export const get = (id) => client.get(`/admin/offers/${id}`).then((r) => r.data);
export const create = (payload) => client.post("/admin/offers", payload).then((r) => r.data);
export const update = (id, payload) => client.patch(`/admin/offers/${id}`, payload).then((r) => r.data);
export const publish = (id) => client.post(`/admin/offers/${id}/publish`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/offers/${id}/reject`).then((r) => r.data);
export const remove = (id) => client.delete(`/admin/offers/${id}`).then((r) => r.data);
