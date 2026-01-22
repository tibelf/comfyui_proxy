#!/bin/bash

# ComfyUI Proxy Test Script
# Usage: ./test.sh [workflow.json] [options]

set -e

# Default values
BASE_URL="${PROXY_URL:-http://localhost:8000}"
DEFAULT_WORKFLOW="workflows/txt2img_basic.json"
DEFAULT_OUTPUT_NODES="9"
POLL_INTERVAL="${POLL_INTERVAL:-2}"
TIMEOUT="${TIMEOUT:-600}"

# Feishu config (can be overridden by environment variables)
FEISHU_APP_TOKEN="${FEISHU_APP_TOKEN:-}"
FEISHU_TABLE_ID="${FEISHU_TABLE_ID:-}"
FEISHU_RECORD_ID="${FEISHU_RECORD_ID:-}"
FEISHU_IMAGE_FIELD="${FEISHU_IMAGE_FIELD:-图片}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 [options] [workflow.json]"
    echo ""
    echo "Arguments:"
    echo "  workflow.json              Path to ComfyUI workflow JSON file (default: workflows/txt2img_basic.json)"
    echo ""
    echo "Options:"
    echo "  -h, --help                 Show this help message"
    echo "  -o, --output-nodes IDS     Comma-separated output node IDs (default: 9)"
    echo "  -u, --url URL              Proxy service URL (default: http://localhost:8000)"
    echo "  --health                   Only check health status"
    echo "  --no-feishu                Skip Feishu upload (dry run)"
    echo "  --timeout SECONDS          Task timeout in seconds (default: 600)"
    echo "  --interval SECONDS         Poll interval in seconds (default: 2)"
    echo ""
    echo "Feishu Options:"
    echo "  --app-token TOKEN          Feishu Bitable app token"
    echo "  --table-id ID              Feishu table ID"
    echo "  --record-id ID             Feishu record ID (optional, for update)"
    echo "  --image-field NAME         Feishu image field name (default: 图片)"
    echo ""
    echo "Environment Variables (alternative to options):"
    echo "  PROXY_URL, FEISHU_APP_TOKEN, FEISHU_TABLE_ID, FEISHU_RECORD_ID, FEISHU_IMAGE_FIELD"
    echo ""
    echo "Examples:"
    echo "  # Health check"
    echo "  $0 --health"
    echo ""
    echo "  # Test with default workflow (no Feishu upload)"
    echo "  $0 --no-feishu"
    echo ""
    echo "  # Specify output nodes"
    echo "  $0 -o 9,10 my_workflow.json --no-feishu"
    echo ""
    echo "  # Full test with Feishu upload"
    echo "  $0 -o 9 --app-token xxx --table-id yyy my_workflow.json"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    if ! command -v curl &> /dev/null; then
        log_error "curl is required but not installed"
        exit 1
    fi
    if ! command -v jq &> /dev/null; then
        log_error "jq is required but not installed"
        echo "Install with: brew install jq (Mac) or apt install jq (Linux)"
        exit 1
    fi
}

health_check() {
    log_info "Checking health at ${BASE_URL}/api/v1/health"

    response=$(curl -s -w "\n%{http_code}" "${BASE_URL}/api/v1/health" 2>/dev/null) || {
        log_error "Failed to connect to proxy service"
        exit 1
    }

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "200" ]; then
        log_error "Health check failed with status $http_code"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        exit 1
    fi

    status=$(echo "$body" | jq -r '.status')
    comfyui=$(echo "$body" | jq -r '.comfyui_available')

    log_success "Proxy service is $status"

    if [ "$comfyui" = "true" ]; then
        log_success "ComfyUI is available"
    else
        log_warn "ComfyUI is NOT available"
    fi

    echo "$body" | jq .
}

submit_task() {
    local workflow_file="$1"
    local no_feishu="$2"

    # Check workflow file exists
    if [ ! -f "$workflow_file" ]; then
        log_error "Workflow file not found: $workflow_file"
        exit 1
    fi

    log_info "Loading workflow from: $workflow_file"

    # Read workflow JSON
    workflow=$(cat "$workflow_file")

    # Validate JSON
    if ! echo "$workflow" | jq . > /dev/null 2>&1; then
        log_error "Invalid JSON in workflow file"
        exit 1
    fi

    # Build feishu config
    if [ "$no_feishu" = "true" ]; then
        # Use dummy values for dry run
        feishu_config=$(jq -n \
            --arg app_token "test_app_token" \
            --arg table_id "test_table_id" \
            --arg image_field "$FEISHU_IMAGE_FIELD" \
            '{app_token: $app_token, table_id: $table_id, image_field: $image_field}')
        log_warn "Running in dry-run mode (no actual Feishu upload)"
    else
        # Check required Feishu config
        if [ -z "$FEISHU_APP_TOKEN" ] || [ -z "$FEISHU_TABLE_ID" ]; then
            log_error "FEISHU_APP_TOKEN and FEISHU_TABLE_ID are required"
            log_info "Set environment variables or use --no-feishu for dry run"
            exit 1
        fi

        feishu_config=$(jq -n \
            --arg app_token "$FEISHU_APP_TOKEN" \
            --arg table_id "$FEISHU_TABLE_ID" \
            --arg record_id "$FEISHU_RECORD_ID" \
            --arg image_field "$FEISHU_IMAGE_FIELD" \
            '{app_token: $app_token, table_id: $table_id, image_field: $image_field} + (if $record_id != "" then {record_id: $record_id} else {} end)')
    fi

    # Build request body
    request_body=$(jq -n \
        --argjson workflow "$workflow" \
        --argjson output_node_ids "$OUTPUT_NODE_IDS" \
        --argjson feishu_config "$feishu_config" \
        --argjson metadata '{"source": "test_script"}' \
        '{workflow: $workflow, output_node_ids: $output_node_ids, feishu_config: $feishu_config, metadata: $metadata}')

    log_info "Submitting task to ${BASE_URL}/api/v1/tasks"

    response=$(curl -s -w "\n%{http_code}" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$request_body" \
        "${BASE_URL}/api/v1/tasks" 2>/dev/null) || {
        log_error "Failed to submit task"
        exit 1
    }

    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')

    if [ "$http_code" != "201" ]; then
        log_error "Task submission failed with status $http_code"
        echo "$body" | jq . 2>/dev/null || echo "$body"
        exit 1
    fi

    task_id=$(echo "$body" | jq -r '.task_id')
    log_success "Task created: $task_id"

    echo "$task_id"
}

poll_task() {
    local task_id="$1"
    local start_time=$(date +%s)
    local last_progress=-1

    log_info "Polling task status (timeout: ${TIMEOUT}s, interval: ${POLL_INTERVAL}s)"
    echo ""

    while true; do
        current_time=$(date +%s)
        elapsed=$((current_time - start_time))

        if [ $elapsed -gt $TIMEOUT ]; then
            log_error "Task timed out after ${TIMEOUT}s"
            exit 1
        fi

        response=$(curl -s "${BASE_URL}/api/v1/tasks/${task_id}" 2>/dev/null) || {
            log_error "Failed to get task status"
            exit 1
        }

        status=$(echo "$response" | jq -r '.status')
        progress=$(echo "$response" | jq -r '.progress')

        # Only print if progress changed
        if [ "$progress" != "$last_progress" ]; then
            printf "\r${BLUE}[STATUS]${NC} %-12s Progress: %3s%% (elapsed: %ds)   " "$status" "$progress" "$elapsed"
            last_progress="$progress"
        fi

        case "$status" in
            "completed")
                echo ""
                echo ""
                log_success "Task completed!"
                echo ""
                echo "Result:"
                echo "$response" | jq '.result'

                record_id=$(echo "$response" | jq -r '.result.feishu_record_id // "N/A"')
                images=$(echo "$response" | jq -r '.result.images | length')

                echo ""
                log_success "Feishu Record ID: $record_id"
                log_success "Images generated: $images"

                return 0
                ;;
            "failed")
                echo ""
                echo ""
                log_error "Task failed!"
                error=$(echo "$response" | jq -r '.error')
                log_error "Error: $error"
                exit 1
                ;;
            "pending"|"processing"|"uploading")
                # Continue polling
                ;;
            *)
                echo ""
                log_error "Unknown status: $status"
                exit 1
                ;;
        esac

        sleep "$POLL_INTERVAL"
    done
}

cancel_task() {
    local task_id="$1"

    log_info "Cancelling task: $task_id"

    response=$(curl -s -w "\n%{http_code}" \
        -X DELETE \
        "${BASE_URL}/api/v1/tasks/${task_id}" 2>/dev/null) || {
        log_error "Failed to cancel task"
        exit 1
    }

    http_code=$(echo "$response" | tail -n1)

    if [ "$http_code" = "204" ]; then
        log_success "Task cancelled successfully"
    else
        body=$(echo "$response" | sed '$d')
        log_error "Failed to cancel task (status: $http_code)"
        echo "$body" | jq . 2>/dev/null || echo "$body"
    fi
}

# Convert comma-separated IDs to JSON array
ids_to_json_array() {
    local ids="$1"
    local json="["
    local first=true
    IFS=',' read -ra ADDR <<< "$ids"
    for id in "${ADDR[@]}"; do
        id=$(echo "$id" | xargs)  # trim whitespace
        if [ "$first" = true ]; then
            first=false
        else
            json+=","
        fi
        json+="\"$id\""
    done
    json+="]"
    echo "$json"
}

# Main
main() {
    local no_feishu=false
    local health_only=false
    local workflow_file=""
    local output_nodes="$DEFAULT_OUTPUT_NODES"

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -h|--help)
                print_usage
                exit 0
                ;;
            -o|--output-nodes)
                output_nodes="$2"
                shift 2
                ;;
            -u|--url)
                BASE_URL="$2"
                shift 2
                ;;
            --health)
                health_only=true
                shift
                ;;
            --no-feishu)
                no_feishu=true
                shift
                ;;
            --timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            --interval)
                POLL_INTERVAL="$2"
                shift 2
                ;;
            --app-token)
                FEISHU_APP_TOKEN="$2"
                shift 2
                ;;
            --table-id)
                FEISHU_TABLE_ID="$2"
                shift 2
                ;;
            --record-id)
                FEISHU_RECORD_ID="$2"
                shift 2
                ;;
            --image-field)
                FEISHU_IMAGE_FIELD="$2"
                shift 2
                ;;
            -*)
                log_error "Unknown option: $1"
                print_usage
                exit 1
                ;;
            *)
                workflow_file="$1"
                shift
                ;;
        esac
    done

    # Set default workflow file if not provided
    if [ -z "$workflow_file" ]; then
        workflow_file="$DEFAULT_WORKFLOW"
    fi

    # Convert output nodes to JSON array
    OUTPUT_NODE_IDS=$(ids_to_json_array "$output_nodes")

    check_dependencies

    echo ""
    echo "=================================="
    echo "  ComfyUI Proxy Test Script"
    echo "=================================="
    echo ""

    if [ "$health_only" = true ]; then
        health_check
        exit 0
    fi

    # Health check first
    health_check
    echo ""

    log_info "Output node IDs: $OUTPUT_NODE_IDS"

    # Submit task
    task_id=$(submit_task "$workflow_file" "$no_feishu")
    echo ""

    # Poll for completion
    poll_task "$task_id"
}

# Handle Ctrl+C
trap 'echo ""; log_warn "Interrupted"; exit 130' INT

main "$@"
