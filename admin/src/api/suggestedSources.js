import client from "./client";

export const list = (params) => client.get("/admin/suggested-sources", { params }).then((r) => r.data);
export const approve = (id) => client.post(`/admin/suggested-sources/${id}/approve`).then((r) => r.data);
export const reject = (id) => client.post(`/admin/suggested-sources/${id}/reject`).then((r) => r.data);
