import client from "./client";

export const list = (params) => client.get("/admin/host-candidates", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/host-candidates/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/host-candidates/${id}/reject`).then((r) => r.data);
