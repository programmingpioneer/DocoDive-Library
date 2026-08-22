-- DocoDive — Database Index Migration
-- Run once against the DocoDive database.
-- If an index already exists, skip that statement.

-- Documents: most-filtered table
CREATE INDEX idx_documents_approved ON documents (approved);
CREATE INDEX idx_documents_category_approved ON documents (category_id, approved);
CREATE INDEX idx_documents_uploaded_by ON documents (uploaded_by);

-- Favorites: user's saved books + toggle lookups
CREATE INDEX idx_favorites_user_id ON favorites (user_id);
CREATE INDEX idx_favorites_book_id ON favorites (book_id);

-- Reviews: book detail page reviews
CREATE INDEX idx_reviews_book_id ON reviews (book_id);

-- User streaks: homepage streak lookup
CREATE INDEX idx_user_streaks_user_id ON user_streaks (user_id);

-- Notifications: user notifications + unread count
CREATE INDEX idx_notifications_user_is_read ON notifications (user_id, is_read);