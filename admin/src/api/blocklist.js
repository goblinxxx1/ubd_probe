import client from "./client";

// Медіа/агрегатор-блоклист (no-fetch список, який віддається краулеру як approved).
export const list = () =>
  client.get("/admin/host-candidates", { params: { status: "approved" } }).then((r) => r.data);
export const create = (host) =>
  client.post("/admin/host-candidates", { host }).then((r) => r.data);
// Розблокувати: approved → rejected знімає хост зі списку (бекенд-ендпоінт /reject).
export const unblock = (id) =>
  client.post(`/admin/host-candidates/${id}/reject`).then((r) => r.data);
