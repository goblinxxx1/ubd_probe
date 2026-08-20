import client from "./client";

export const list = (params) => client.get("/admin/query-terms", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/query-terms/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/query-terms/${id}/reject`).then((r) => r.data);
