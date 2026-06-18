-- Migration 009: add upload_comment to document table
-- Allows OA-Operator to annotate a batch at upload time (e.g. "Q1 FY25 salary slips — north region")

ALTER TABLE document
  ADD COLUMN IF NOT EXISTS upload_comment TEXT;

ALTER TABLE document
  ADD COLUMN IF NOT EXISTS original_filename TEXT;
