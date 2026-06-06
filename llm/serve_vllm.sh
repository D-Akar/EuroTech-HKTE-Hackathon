#!/usr/bin/env bash
# Launch a vLLM OpenAI-compatible server for the querying pipeline.
#
# Defaults are tuned for an 8 GB GPU (RTX 4060 Laptop) using a 4-bit AWQ model.
# Override anything via env vars, e.g.:
#   VLLM_MODEL=Qwen/Qwen2.5-3B-Instruct-AWQ bash llm/serve_vllm.sh
#
# The server listens on :8001 (the FastAPI backend owns :8000).
set -euo pipefail

MODEL="${VLLM_MODEL:-Qwen/Qwen2.5-7B-Instruct-AWQ}"
PORT="${VLLM_PORT:-8001}"
# 4096 + 0.95 util fits the 7B AWQ weights (~5.2 GiB) plus KV cache in 8 GB.
# (8192 leaves too little KV room on this card.)
MAX_LEN="${VLLM_MAX_MODEL_LEN:-4096}"
GPU_UTIL="${VLLM_GPU_UTIL:-0.95}"
QUANT="${VLLM_QUANTIZATION:-awq_marlin}"

# Use vLLM's bundled FlashAttention. It supports paged-decode attention; the
# xformers backend does NOT on this build (its FA2/cutlass kernels reject the
# paged KV mask). flashinfer is uninstalled here (its cubin filenames are too
# long for the ecryptfs home), so FLASH_ATTN is the right choice on this Ada GPU.
export VLLM_ATTENTION_BACKEND="${VLLM_ATTENTION_BACKEND:-FLASH_ATTN}"

echo "Serving $MODEL on :$PORT (max_len=$MAX_LEN, gpu_util=$GPU_UTIL, quant=$QUANT)"

exec vllm serve "$MODEL" \
  --port "$PORT" \
  --quantization "$QUANT" \
  --dtype float16 \
  --max-model-len "$MAX_LEN" \
  --gpu-memory-utilization "$GPU_UTIL" \
  --enforce-eager
