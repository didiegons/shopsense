import importlib
import os
from copy import deepcopy

from app.models.intent import IntentRequest, ParsedShoppingIntent, VertexIntentOutput


class VertexIntentError(Exception):
    """Expected configuration, transport, or model failures eligible for fallback."""


class VertexIntentAdapter:
    def __init__(self, project: str, location: str, model: str) -> None:
        self.project = project
        self.location = location
        self.model = model
        self._client = None
        self._sdk = None

    @classmethod
    def from_environment(cls) -> "VertexIntentAdapter | None":
        project = os.getenv("VERTEX_AI_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
        location = os.getenv("VERTEX_AI_REGION") or os.getenv("GOOGLE_CLOUD_LOCATION")
        model = os.getenv("SHOPSENSE_INTENT_MODEL")
        if not project or not location or not model:
            return None
        return cls(project=project, location=location, model=model)

    def parse(self, request: IntentRequest) -> ParsedShoppingIntent:
        genai, types, sdk_errors, google_auth_errors = self._load_sdk()
        expected_client_errors = (
            sdk_errors.APIError,
            google_auth_errors.GoogleAuthError,
            OSError,
            TimeoutError,
            ValueError,
        )
        if self._client is None:
            try:
                self._client = genai.Client(
                    vertexai=True,
                    project=self.project,
                    location=self.location,
                )
            except expected_client_errors as error:
                raise VertexIntentError("Unable to initialize Vertex AI client") from error

        category_context = request.category or "not specified"
        prompt = (
            "Extract only requirements and preferences explicitly supported by the query. "
            "Do not produce product facts or recommendations. Separate hard constraints "
            "from preferences. For attributes that depend on the requested product category, "
            "put mandatory attributes in category_hard_constraints and stated softer choices in "
            "category_preferences. Use one descriptive attribute key per value, preserve the "
            "query's value, and do not put category attributes in use_case. Do not leave these "
            "maps empty when the query clearly states category-specific attributes. For example, "
            "'full-frame sensor' maps to category_hard_constraints.sensor_format='full-frame', "
            "while 'preferably mirrorless' maps to category_preferences.body_style='mirrorless'. "
            "These are examples of the generic mapping, not a closed list of categories or keys. "
            "Bare Windows means family Windows with no version; explicit Windows 11 includes version 11. "
            "Set clarification_needed and ask a concise question when a value or constraint strength "
            "is ambiguous. Use the supplied query verbatim as original_query and the supplied category.\n"
            f"Category: {category_context}\n"
            f"Query: {request.query}"
        )
        try:
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=_vertex_schema(VertexIntentOutput),
                ),
            )
        except (
            sdk_errors.APIError,
            google_auth_errors.GoogleAuthError,
            OSError,
            TimeoutError,
        ) as error:
            raise VertexIntentError("Vertex AI intent request failed") from error
        if not response.text:
            raise VertexIntentError("Vertex AI returned an empty intent response")
        wire_output = VertexIntentOutput.model_validate_json(response.text)
        hard_category_values = {
            entry.attribute: entry.value
            for entry in wire_output.category_hard_constraint_entries
        }
        preference_category_values = {
            entry.attribute: entry.value
            for entry in wire_output.category_preference_entries
        }
        return ParsedShoppingIntent(
            original_query=request.query,
            category=request.category or wire_output.category,
            hard_constraints=wire_output.hard_constraints,
            preferences=wire_output.preferences,
            category_hard_constraints=hard_category_values,
            category_preferences=preference_category_values,
            parser_source="vertex_ai",
            clarification_needed=wire_output.clarification_needed,
            clarification_question=wire_output.clarification_question,
            confidence=wire_output.confidence,
            evidence=wire_output.evidence,
        )

    def _load_sdk(self):
        if self._sdk is None:
            try:
                genai = importlib.import_module("google.genai")
                types = importlib.import_module("google.genai.types")
                sdk_errors = importlib.import_module("google.genai.errors")
                google_auth_errors = importlib.import_module("google.auth.exceptions")
            except ImportError as error:
                raise VertexIntentError("Google GenAI SDK is unavailable") from error
            self._sdk = (genai, types, sdk_errors, google_auth_errors)
        return self._sdk


def _vertex_schema(model: type[ParsedShoppingIntent]) -> dict[str, object]:
    schema = deepcopy(model.model_json_schema())
    definitions = schema.pop("$defs", {})

    def inline_supported_schema(node: object) -> None:
        if isinstance(node, dict):
            reference = node.pop("$ref", None)
            if reference:
                definition_name = reference.rsplit("/", 1)[-1]
                node.update(deepcopy(definitions[definition_name]))
            if "exclusiveMinimum" in node:
                node["minimum"] = node.pop("exclusiveMinimum")
            if "exclusiveMaximum" in node:
                node["maximum"] = node.pop("exclusiveMaximum")
            for value in list(node.values()):
                inline_supported_schema(value)
        elif isinstance(node, list):
            for value in node:
                inline_supported_schema(value)

    inline_supported_schema(schema)
    return schema