"""
Startup script to register custom recognizers with Presidio Analyzer.

This script creates a Flask app with custom recognizers registered.
Uses the actual Presidio server components with multi-language support.
"""

import logging
import os
import sys
from typing import Any, Dict, List, Optional

try:
    from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
    from presidio_analyzer.nlp_engine import NlpEngineProvider
except ImportError as exc:  # pragma: no cover - runtime dependency check
    AnalyzerEngine = None
    RecognizerRegistry = None
    NlpEngineProvider = None
    PRESIDIO_IMPORT_ERROR = exc
else:
    PRESIDIO_IMPORT_ERROR = None

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


ENTITY_ALIASES = {
    "PERSON_ZH": "PERSON",
    "PERSON_CHINESE": "PERSON",
}


def _extract_analyze_payload(raw_data: Any) -> Optional[Dict[str, Any]]:
    """Extract analyze payload from supported request shapes.

    Supported:
    - {"text": "...", "language": "en", "entities": [...]} 
    - {"presidioBody": {...}}
    - [{"presidioBody": {...}}]
    - [{"text": "...", ...}]
    """
    if raw_data is None:
        return None

    data = raw_data
    if isinstance(data, list):
        if not data:
            return None
        data = data[0]

    if not isinstance(data, dict):
        return None

    if "presidioBody" in data and isinstance(data["presidioBody"], dict):
        data = data["presidioBody"]

    return data if isinstance(data, dict) else None


def _normalize_entities(language: str, entities: Optional[List[str]], analyzer_engine: Any) -> Optional[List[str]]:
    """Map known aliases and keep only entities supported for the selected language."""
    if entities is None:
        return None

    if not isinstance(entities, list):
        return None

    supported = set(analyzer_engine.get_supported_entities(language=language))
    normalized: List[str] = []

    for entity in entities:
        if not isinstance(entity, str):
            continue

        mapped = ENTITY_ALIASES.get(entity, entity)

        # Keep ADDRESS_ZH only for Chinese; map to ADDRESS_EN for English.
        if mapped == "ADDRESS_ZH" and language != "zh":
            mapped = "ADDRESS_EN"

        if mapped in supported and mapped not in normalized:
            normalized.append(mapped)

    return normalized

def create_custom_analyzer():
    """Create AnalyzerEngine with built-in AND custom recognizers."""
    if PRESIDIO_IMPORT_ERROR is not None:
        raise RuntimeError(f"Presidio Analyzer is not installed: {PRESIDIO_IMPORT_ERROR}") from PRESIDIO_IMPORT_ERROR

    from recognizers.hk_patterns import get_all_recognizers

    logger.info("Creating recognizer registry with built-in recognizers...")
    registry = RecognizerRegistry()

    # Load all built-in recognizers (PERSON, LOCATION, EMAIL_ADDRESS, etc.)
    try:
        registry.load_predefined_recognizers()
        logger.info("Loaded built-in Presidio recognizers")
    except Exception as exc:
        logger.warning("Could not load predefined recognizers: %s", exc)
    
    # Set supported languages where supported by the installed version
    try:
        registry.supported_languages = ["en", "zh"]
    except Exception as exc:  # pragma: no cover - compatibility across Presidio versions
        logger.warning("Could not set registry supported_languages: %s", exc)
    
    # Add custom HK recognizers
    custom_recognizers = get_all_recognizers()
    logger.info(f"Found {len(custom_recognizers)} custom HK recognizers")
    
    for recognizer in custom_recognizers:
        registry.add_recognizer(recognizer)
        logger.info(f"Registered: {recognizer.name} -> {recognizer.supported_entities}")
    
    # Create NLP engine with both English and Chinese support
    logger.info("Creating NLP engine with multi-language support...")
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "en", "model_name": "en_core_web_lg"},
            {"lang_code": "zh", "model_name": "zh_core_web_lg"}
        ]
    }
    
    nlp_engine_provider = NlpEngineProvider(nlp_configuration=nlp_config)
    nlp_engine = nlp_engine_provider.create_engine()
    
    # Create analyzer engine with custom registry and NLP engine
    logger.info("Creating AnalyzerEngine...")
    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en", "zh"]
    )
    
    # Log supported entities by language
    for lang in ["en", "zh"]:
        entities = analyzer.get_supported_entities(language=lang)
        logger.info(f"Supported entities for {lang}: {sorted(entities)}")
    
    return analyzer

def create_app(analyzer_engine=None):
    """Create Flask app with custom analyzer."""
    from flask import Flask, request, jsonify
    
    app = Flask(__name__)
    
    # Use provided analyzer or create default
    if analyzer_engine is None:
        analyzer_engine = create_custom_analyzer()
    
    @app.route('/health', methods=['GET'])
    def health():
        return jsonify({"status": "healthy"})
    
    @app.route('/analyze', methods=['POST'])
    def analyze():
        try:
            data = _extract_analyze_payload(request.get_json(silent=True))
            if not data:
                return jsonify({"error": "No JSON data provided"}), 400
            
            text = data.get('text', '')
            language = data.get('language', 'en')
            entities = _normalize_entities(language, data.get('entities', None), analyzer_engine)
            
            if not text:
                return jsonify({"error": "No text provided"}), 400
            
            # Analyze text
            results = analyzer_engine.analyze(
                text=text,
                language=language,
                entities=entities
            )
            
            # Convert to JSON-serializable format
            output = []
            for result in results:
                output.append({
                    "entity_type": result.entity_type,
                    "start": result.start,
                    "end": result.end,
                    "score": result.score,
                    "analysis_explanation": None
                })
            
            return jsonify(output)
        
        except Exception as e:
            logger.error(f"Error in analyze: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500
    
    @app.route('/supportedentities', methods=['GET'])
    def supported_entities():
        language = request.args.get('language', 'en')
        entities = analyzer_engine.get_supported_entities(language=language)
        return jsonify({
            "language": language,
            "entities": list(entities)
        })
    
    return app

def main():
    """Main entry point."""
    try:
        logger.info("Starting Presidio Analyzer with custom HK recognizers...")
        
        # Create custom analyzer
        analyzer = create_custom_analyzer()
        
        # Create Flask app
        app = create_app(analyzer_engine=analyzer)
        
        # Get port from environment
        port = int(os.environ.get("PORT", 3000))
        host = os.environ.get("HOST", "0.0.0.0")
        
        logger.info(f"Server starting on {host}:{port}")
        logger.info("Ready to accept requests!")
        
        # Start the Flask app
        app.run(host=host, port=port, debug=False, threaded=True)
        
    except Exception as e:
        logger.error(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)

def test_recognizers():
    """Test function to verify recognizers work correctly."""
    if PRESIDIO_IMPORT_ERROR is not None:
        raise RuntimeError(f"Presidio Analyzer is not installed: {PRESIDIO_IMPORT_ERROR}") from PRESIDIO_IMPORT_ERROR

    from recognizers.hk_patterns import get_all_recognizers
    
    print("\n" + "="*60)
    print("TESTING CUSTOM RECOGNIZERS")
    print("="*60)
    
    registry = RecognizerRegistry()
    for recognizer in get_all_recognizers():
        registry.add_recognizer(recognizer)
        print(f"✓ Registered: {recognizer.name}")
    
    # Create NLP engine with both languages
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "en", "model_name": "en_core_web_lg"},
            {"lang_code": "zh", "model_name": "zh_core_web_lg"}
        ]
    }
    nlp_engine_provider = NlpEngineProvider(nlp_configuration=nlp_config)
    nlp_engine = nlp_engine_provider.create_engine()
    
    analyzer = AnalyzerEngine(registry=registry, nlp_engine=nlp_engine, supported_languages=["en", "zh"])
    
    # Test cases
    test_cases = [
        ("My HKID is Y123456(7)", "en", None),
        ("Passport: K12345678", "en", None),
        ("Call me at +852 9123 4567", "en", None),
        ("Account: 123-456789-001", "en", None),
        ("Student ID: 55912345", "en", None),
        ("發明人：陳大文博士", "zh", None),
        ("地址：香港九龍旺角彌敦道700號", "zh", None),
    ]
    
    for text, language, entities in test_cases:
        print(f"\nTest: '{text[:50]}...' [{language}]")
        try:
            results = analyzer.analyze(text=text, language=language, entities=entities)
            if results:
                for r in results:
                    entity_text = text[r.start:r.end]
                    print(f"  ✓ Found {r.entity_type}: '{entity_text}' (score: {r.score:.2f})")
            else:
                print(f"  ✗ No entities detected")
        except Exception as e:
            print(f"  ✗ Error: {e}")
    
    print("\n" + "="*60)

if __name__ == "__main__":
    # Check if test mode
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        test_recognizers()
    else:
        main()
