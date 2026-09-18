-- ============================================================
-- DocoDive — All Schema Changes (single-file migration)
-- ============================================================
-- KAISE USE KAREIN:
--   1. Naya change? Is file ke NEECHE (sabse aakhir me) SQL likho.
--   2. Har statement ke baad SEMICOLON (;) zaroori hai.
--   3. Purani lines KABHI edit mat karo — bas neeche add karo.
--   4. Terminal me: python scripts\run_all.py
--   5. Script khud pehchan legi konsa statement naya hai.
-- ============================================================
-- Example:
--   ALTER TABLE documents ADD COLUMN bookmarks INT DEFAULT 0;
--   CREATE INDEX idx_bookmarks ON documents(bookmarks);
-- ============================================================

-- ============ NEECHE APNA NAYA SQL LIKHO ============
-- (Ye line ke baad, ek-ek statement likho, semicolon ke saath)

