#!/usr/bin/env node

import { readFile, stat } from "node:fs/promises";
import {
  REPORT_HTML_POLICY,
  assembleReportV3,
  prepareEvaluationV3,
  validateReport
} from "./evaluation-report-core.mjs";

const MAX_INPUT_BYTES = 1_000_000;

async function readStdin() {
  let source = "";
  let bytes = 0;
  process.stdin.setEncoding("utf8");
  for await (const chunk of process.stdin) {
    bytes += Buffer.byteLength(chunk, "utf8");
    if (bytes > MAX_INPUT_BYTES) throw new RangeError(`输入超过 ${MAX_INPUT_BYTES} 字节限制`);
    source += chunk;
  }
  return source;
}

async function readJson(path) {
  let source;
  if (path === "-") {
    source = await readStdin();
  } else {
    const info = await stat(path);
    if (info.size > MAX_INPUT_BYTES) throw new RangeError(`输入超过 ${MAX_INPUT_BYTES} 字节限制`);
    source = await readFile(path, "utf8");
  }
  return JSON.parse(source);
}

function writeJson(value) {
  process.stdout.write(`${JSON.stringify(value, null, 2)}\n`);
}

function usage() {
  return [
    "Usage:",
    "  node evaluation-report-cli.mjs prepare [input.json|-]",
    "  node evaluation-report-cli.mjs validate [input.json|-]",
    "  node evaluation-report-cli.mjs assemble [input.json|-]",
    "",
    "prepare input: a V3 formData object, or { \"formData\": {...} }",
    "validate input: { \"formData\": {...}, \"html\": \"<h1>...</h1>\" }",
    "assemble input: { \"formData\": {...}, \"sanitizedHtml\": \"<h1>...</h1>\" }"
  ].join("\n");
}

async function main() {
  const mode = process.argv[2] || "prepare";
  if (mode === "--help" || mode === "-h") {
    process.stdout.write(`${usage()}\n`);
    return;
  }

  const payload = await readJson(process.argv[3] || "-");
  const formData = payload.formData ?? payload;
  const prepared = prepareEvaluationV3(formData);

  if (mode === "prepare") {
    writeJson(prepared);
    return;
  }

  if (mode === "validate") {
    if (typeof payload.html !== "string") throw new TypeError("validate 模式需要 html 字符串");
    const reportValidation = validateReport(payload.html, prepared.bundle.scores, formData);
    writeJson({
      schemaVersion: 3,
      contractVersion: prepared.contractVersion,
      sourceRulesetVersion: prepared.sourceRulesetVersion,
      rulesetVersion: prepared.rulesetVersion,
      knowledgeVersion: prepared.knowledgeVersion,
      privacy: prepared.privacy,
      inputValidation: prepared.inputValidation,
      reportValidation,
      reportStatus: reportValidation.passed ? "awaiting-host-sanitization" : "review-required",
      corePublishable: false,
      reviewRequired: !reportValidation.passed,
      candidateHtml: reportValidation.cleaned,
      sanitizationPolicy: REPORT_HTML_POLICY,
      htmlSafety: "untrusted-awaiting-host-sanitizer"
    });
    return;
  }

  if (mode === "assemble") {
    if (typeof payload.sanitizedHtml !== "string") throw new TypeError("assemble 模式需要 sanitizedHtml 字符串");
    if (Object.hasOwn(payload, "brandContent")) throw new TypeError("CLI 不接受 brandContent；品牌 HTML 只能由 JavaScript 宿主的可信配置注入");
    const reportValidation = validateReport(payload.sanitizedHtml, prepared.bundle.scores, formData);
    const corePublishable = reportValidation.passed;
    writeJson({
      schemaVersion: 3,
      contractVersion: prepared.contractVersion,
      sourceRulesetVersion: prepared.sourceRulesetVersion,
      rulesetVersion: prepared.rulesetVersion,
      knowledgeVersion: prepared.knowledgeVersion,
      privacy: prepared.privacy,
      inputValidation: prepared.inputValidation,
      reportValidation,
      reportStatus: corePublishable ? "ready-for-host-gates" : "review-required",
      corePublishable,
      reviewRequired: !corePublishable,
      reportContent: corePublishable ? assembleReportV3(formData, prepared.bundle.scores, payload.sanitizedHtml) : null,
      htmlSafety: corePublishable ? "host-asserted-sanitized-trusted-template" : "rejected-sanitized-candidate"
    });
    return;
  }

  throw new TypeError(`未知模式：${mode}\n${usage()}`);
}

main().catch(error => {
  process.stderr.write(`evaluation-report: ${error.message}\n`);
  process.exitCode = 1;
});
