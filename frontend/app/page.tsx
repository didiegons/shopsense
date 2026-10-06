"use client";

import { FormEvent, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { extractIntent, searchProducts } from "../lib/api";
import type {
  JsonValue,
  ParsedShoppingIntent,
  Product,
  SearchFilters,
  SearchResponse,
} from "../lib/types";
import styles from "./page.module.css";

function formatJsonValue(value: JsonValue): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return value.map(formatJsonValue).join(", ");
  if (typeof value === "object") {
    return Object.entries(value).map(([key, item]) => `${key}: ${formatJsonValue(item)}`).join(", ");
  }
  return String(value);
}

function formatCategoryValues(values: Record<string, JsonValue>): string | null {
  const entries = Object.entries(values).map(
    ([key, value]) => `${key.replaceAll("_", " ")}: ${formatJsonValue(value)}`,
  );
  return entries.length > 0 ? entries.join(" · ") : null;
}

function formatProductSpecifications(product: Product): string {
  const specifications = product.specifications;
  const laptopValues = [
    specifications.processor,
    specifications.ram_gb != null ? `${specifications.ram_gb} GB RAM` : null,
    specifications.storage_gb != null ? `${specifications.storage_gb} GB storage` : null,
    specifications.weight_kg != null ? `${specifications.weight_kg} kg` : null,
    specifications.operating_system,
  ].filter((value): value is string => Boolean(value));
  const categoryValues = Object.entries(product.category_attributes ?? {}).map(
    ([key, value]) => `${key.replaceAll("_", " ")}: ${formatJsonValue(value)}`,
  );
  return [...laptopValues, ...categoryValues].join(" · ") || "No structured specifications listed";
}

export default function Home() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<SearchFilters>({});
  const [intent, setIntent] = useState<ParsedShoppingIntent | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [intentError, setIntentError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isInterpreting, setIsInterpreting] = useState(false);
  const [applyOperatingSystem, setApplyOperatingSystem] = useState(true);
  const [allowUnresolvedIntent, setAllowUnresolvedIntent] = useState(false);

  async function handleInterpret(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsInterpreting(true);
    setIntentError(null);
    setError(null);
    setResponse(null);
    try {
      const parsedIntent = await extractIntent(query);
      setIntent(parsedIntent);
      setAllowUnresolvedIntent(false);
      const hardOperatingSystem = parsedIntent.hard_constraints.operating_system;
      const preferredOperatingSystem = parsedIntent.preferences.operating_system;
      setFilters({
        max_budget: parsedIntent.hard_constraints.max_budget ?? undefined,
        min_ram_gb: parsedIntent.hard_constraints.min_ram_gb ?? undefined,
        max_weight_kg: parsedIntent.hard_constraints.max_weight_kg ?? undefined,
        operating_system: hardOperatingSystem ?? preferredOperatingSystem ?? undefined,
      });
      setApplyOperatingSystem(Boolean(hardOperatingSystem));
    } catch (intentRequestError) {
      setIntent(null);
      setIntentError(intentRequestError instanceof Error ? intentRequestError.message : "Could not interpret request.");
    } finally {
      setIsInterpreting(false);
    }
  }

  async function handleSearch() {
    setIsLoading(true);
    setError(null);
    if (intent?.clarification_needed && !allowUnresolvedIntent) {
      setError("Resolve the clarification or confirm that search should use only the visible filters.");
      setIsLoading(false);
      return;
    }
    try {
      setResponse(
        await searchProducts({
          ...filters,
          operating_system: applyOperatingSystem ? filters.operating_system : undefined,
        }),
      );
    } catch (searchError) {
      setResponse(null);
      setError(searchError instanceof Error ? searchError.message : "Search failed.");
    } finally {
      setIsLoading(false);
    }
  }

  function updateFilter<K extends keyof SearchFilters>(key: K, value: SearchFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="ShopSense AI home">
          ShopSense<span> AI</span>
        </Link>
      </header>
      <section className={styles.searchSection} aria-labelledby="page-title">
        <p className={styles.eyebrow}>PRODUCT DISCOVERY, MADE CLEAR</p>
        <h1 id="page-title">Find the right laptop for what you do.</h1>
        <p className={styles.description}>
          Compare product details and explore options that fit your budget and needs.
        </p>
        <form className={styles.searchForm} onSubmit={handleInterpret}>
          <label className={styles.queryLabel} htmlFor="natural-query">
            What are you looking for?
          </label>
          <input
            id="natural-query"
            className={styles.queryInput}
            type="text"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. A lightweight laptop under $1,000 for cybersecurity school"
          />
          <button className={styles.secondaryButton} type="submit" disabled={isInterpreting || !query.trim()}>
            {isInterpreting ? "Interpreting..." : "Interpret requirements"}
          </button>
          {intentError && <p className={styles.error} role="alert">{intentError}</p>}

          {intent && (
            <section className={styles.intentPanel} aria-live="polite" aria-labelledby="intent-title">
              <div className={styles.intentHeading}>
                <div>
                  <p className={styles.eyebrow}>
                    {intent.parser_source === "vertex_ai" ? "AI-ASSISTED INTERPRETATION" : "DETERMINISTIC FALLBACK"}
                  </p>
                  <h2 id="intent-title">Requirements from your request</h2>
                </div>
                {intent.clarification_needed && <span className={styles.clarificationTag}>Needs clarification</span>}
              </div>
              <p className={styles.intentQuery}>“{intent.original_query}”</p>
              {intent.clarification_question && (
                <div className={styles.clarification} role="status">
                  <p>{intent.clarification_question}</p>
                  <label className={styles.confirmUnresolved}>
                    <input
                      type="checkbox"
                      checked={allowUnresolvedIntent}
                      onChange={(event) => setAllowUnresolvedIntent(event.target.checked)}
                    />
                    Search with only the visible filters; unresolved details will not be applied
                  </label>
                </div>
              )}
              <div className={styles.intentDetails}>
                {intent.category && <p><strong>Category:</strong> {intent.category}</p>}
                <p>
                  <strong>Hard constraints:</strong>{" "}
                  {[
                    intent.hard_constraints.max_budget !== null
                      ? `Budget up to $${intent.hard_constraints.max_budget}`
                      : null,
                    intent.hard_constraints.min_ram_gb !== null
                      ? `RAM at least ${intent.hard_constraints.min_ram_gb} GB`
                      : null,
                    intent.hard_constraints.max_weight_kg !== null
                      ? `Weight up to ${intent.hard_constraints.max_weight_kg} kg`
                      : null,
                    intent.hard_constraints.operating_system
                      ? `OS ${intent.hard_constraints.operating_system}`
                      : null,
                    formatCategoryValues(intent.category_hard_constraints),
                  ].filter(Boolean).join(" · ") || "None identified"}
                </p>
                <p>
                  <strong>Preferences:</strong>{" "}
                  {[
                    intent.preferences.operating_system
                      ? `OS ${intent.preferences.operating_system}`
                      : null,
                    intent.preferences.use_case,
                    intent.preferences.portability_preference,
                    intent.preferences.storage_preference_gb
                      ? `${intent.preferences.storage_preference_gb} GB storage`
                      : null,
                    formatCategoryValues(intent.category_preferences),
                  ].filter(Boolean).join(" · ") || "None identified"}
                </p>
                {intent.evidence.length > 0 && (
                  <p><strong>Matched phrases:</strong> {intent.evidence.join(" · ")}</p>
                )}
                <p>
                  <strong>Parser:</strong> {intent.parser_source === "vertex_ai" ? "Vertex AI" : "Deterministic fallback"}
                  {intent.deterministic_agreement !== null
                    ? ` · ${intent.deterministic_agreement ? "agrees" : `differs on ${intent.differing_fields.join(", ")}`}`
                    : ""}
                  {` · confidence ${(intent.confidence * 100).toFixed(0)}%`}
                </p>
              </div>
              <p className={styles.note}>
                Edit the fields below before searching. Product results still come only from the catalog.
              </p>
            </section>
          )}

          <div className={styles.filterHeading}>
            <h2>{intent ? "Editable search requirements" : "Structured filters"}</h2>
            <p>Only these visible values are sent to product search.</p>
          </div>
          <div className={styles.filters}>
            <label>
              Maximum budget (USD)
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Any"
                value={filters.max_budget ?? ""}
                onChange={(event) =>
                  updateFilter("max_budget", event.target.value ? Number(event.target.value) : undefined)
                }
              />
            </label>
            <label>
              Minimum RAM (GB)
              <input
                type="number"
                min="1"
                step="1"
                placeholder="Any"
                value={filters.min_ram_gb ?? ""}
                onChange={(event) =>
                  updateFilter("min_ram_gb", event.target.value ? Number(event.target.value) : undefined)
                }
              />
            </label>
            <label>
              Maximum weight (kg)
              <input
                type="number"
                min="0.1"
                step="0.1"
                placeholder="Any"
                value={filters.max_weight_kg ?? ""}
                onChange={(event) =>
                  updateFilter("max_weight_kg", event.target.value ? Number(event.target.value) : undefined)
                }
              />
            </label>
            <label>
              Operating system{intent?.hard_constraints.operating_system ? " requirement" : intent?.preferences.operating_system ? " preference" : ""}
              <select
                value={filters.operating_system ?? ""}
                onChange={(event) => {
                  updateFilter("operating_system", event.target.value || undefined);
                  setApplyOperatingSystem(true);
                }}
              >
                <option value="">Any</option>
                <option value="Windows">Windows (any version)</option>
                <option value="Windows 11">Windows 11</option>
                <option value="Ubuntu Linux">Ubuntu Linux</option>
                <option value="ChromeOS">ChromeOS</option>
              </select>
            </label>
          </div>
          {intent?.preferences.operating_system && !intent.hard_constraints.operating_system && (
            <label className={styles.osToggle}>
              <input
                type="checkbox"
                checked={applyOperatingSystem}
                onChange={(event) => setApplyOperatingSystem(event.target.checked)}
              />
              Apply this OS preference as a hard search filter
            </label>
          )}
          <button className={styles.searchButton} type="button" onClick={handleSearch} disabled={isLoading}>
            {isLoading ? "Searching..." : "Search products"}
          </button>
        </form>
      </section>
      <section className={styles.resultsSection} aria-live="polite" aria-labelledby="results-title">
        <div className={styles.resultsHeading}>
          <h2 id="results-title">Results</h2>
          {response && <p>{response.total} demo products</p>}
        </div>
        {error && <p className={styles.error} role="alert">{error}</p>}
        {!response && !error && (
          <p className={styles.emptyState}>Your matching products will appear here.</p>
        )}
        {response && response.total === 0 && (
          <p className={styles.emptyState}>No demo products match all of those filters.</p>
        )}
        {response && response.results.length > 0 && (
          <ul className={styles.resultsList}>
            {response.results.map((product) => (
              <li className={styles.product} key={product.product_id}>
                <div className={styles.productCard}>
                  <div className={styles.productMedia}>
                    <span className={styles.imageFallback} aria-hidden="true">
                      Demo image unavailable
                    </span>
                    {product.image_url && (
                      <Image
                        className={styles.productImage}
                        src={product.image_url}
                        alt={`Generic demo laptop illustration for ${product.model_name}`}
                        fill
                        sizes="(max-width: 440px) 100vw, (max-width: 700px) 132px, 176px"
                        loading="lazy"
                        onError={(event) => {
                          event.currentTarget.hidden = true;
                        }}
                      />
                    )}
                  </div>
                  <div className={styles.productContent}>
                    <div className={styles.productHeading}>
                      <div>
                        <p className={styles.brandName}>{product.brand}</p>
                        <h3>{product.model_name}</h3>
                      </div>
                      <p className={styles.price}>
                        {new Intl.NumberFormat("en-US", {
                          style: "currency",
                          currency: product.offer.currency,
                          maximumFractionDigits: 0,
                        }).format(product.offer.price)}
                      </p>
                    </div>
                    <p className={styles.specifications}>
                      {formatProductSpecifications(product)}
                    </p>
                    <p className={styles.provenance}>
                      Demo data · availability: {product.offer.availability.replaceAll("_", " ")} · checked{" "}
                      {product.offer.source.source_checked_date}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
