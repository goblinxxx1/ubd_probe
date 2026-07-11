import client from "./client";

export const list = (params) => client.get("/offers", { params }).then((r) => r.data);
export const get = (id) => client.get(`/offers/${id}`).then((r) => r.data);
