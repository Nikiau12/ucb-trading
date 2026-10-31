DROP INDEX IF EXISTS payment_invoices_open_amount;

UPDATE payment_invoices
SET expected_amount = base_amount
WHERE status = 'open'
  AND expected_amount <> base_amount;
