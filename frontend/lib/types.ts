export type JsonValue =
  | string
  | number
  | boolean
  | null
  | JsonValue[]
  | { [key: string]: JsonValue };

export type SearchFilters = {
  max_budget?: number;
  min_ram_gb?: number;
  operating_system?: string;
  max_weight_kg?: number;
  category_filters?: Record<string, JsonValue>;
};

export type AppliedFilters = {
  max_budget: number | null;
  min_ram_gb: number | null;
  operating_system: string | null;
  max_weight_kg: number | null;
};

export type DataSource = {
  source_name: string;
  source_url: string;
  source_checked_date: string;
  data_status: "demo" | "live";
};

export type Product = {
  product_id: string;
  brand: string;
  model_name: string;
  category: string;
  image_url?: string | null;
  specifications: {
    processor?: string | null;
    ram_gb?: number | null;
    storage_gb?: number | null;
    weight_kg?: number | null;
    operating_system?: string | null;
  };
  category_attributes?: Record<string, JsonValue> | null;
  rating: number | null;
  offer: {
    price: number;
    currency: string;
    availability: "in_stock" | "out_of_stock" | "unknown";
    source: DataSource;
  };
};

export type SearchResponse = {
  results: Product[];
  total: number;
  applied_filters: AppliedFilters;
};

export type ParsedShoppingIntent = {
  original_query: string;
  category: string | null;
  hard_constraints: {
    max_budget: number | null;
    min_ram_gb: number | null;
    max_weight_kg: number | null;
    operating_system: string | null;
    operating_system_family: string | null;
    operating_system_version: string | null;
  };
  category_hard_constraints: Record<string, JsonValue>;
  preferences: {
    operating_system: string | null;
    operating_system_family: string | null;
    operating_system_version: string | null;
    use_case: string | null;
    portability_preference: "lightweight" | "balanced" | "performance" | null;
    storage_preference_gb: number | null;
  };
  category_preferences: Record<string, JsonValue>;
  parser_source: "deterministic" | "vertex_ai";
  deterministic_agreement: boolean | null;
  differing_fields: string[];
  clarification_needed: boolean;
  clarification_question: string | null;
  confidence: number;
  evidence: string[];
};
