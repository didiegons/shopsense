import type { ParsedShoppingIntent, SearchFilters, SearchResponse } from "./types";

const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function extractIntent(query: string, category?: string): Promise<ParsedShoppingIntent> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/intent`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, ...(category ? { category } : {}) }),
    });
  } catch {
    throw new Error("Could not reach the ShopSense service to interpret your request. Check that the backend is running and try again.");
  }

  if (!response.ok) {
    if (response.status === 422) {
      throw new Error("Enter a non-empty request of 1,000 characters or fewer.");
    }
    throw new Error(`Intent request failed (${response.status}). Is the backend running?`);
  }

  return (await response.json()) as ParsedShoppingIntent;
}

export async function searchProducts(filters: SearchFilters): Promise<SearchResponse> {
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}/api/v1/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(filters),
    });
  } catch {
    throw new Error("Could not reach the ShopSense service to search products. Check that the backend is running and try again.");
  }

  if (!response.ok) {
    if (response.status === 422) {
      throw new Error("One or more filters are invalid. Check the values and try again.");
    }
    throw new Error(`Search request failed (${response.status}). Is the backend running?`);
  }

  return (await response.json()) as SearchResponse;
}
