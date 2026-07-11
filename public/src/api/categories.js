import client from "./client";

export const listTarget = () => client.get("/target-categories").then((r) => r.data);
export const listOffer = () => client.get("/offer-categories").then((r) => r.data);
