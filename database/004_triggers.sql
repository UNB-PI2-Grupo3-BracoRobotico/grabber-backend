CREATE OR REPLACE FUNCTION check_product_amount() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.product_amount = 0 THEN
        DELETE FROM product WHERE product_id = OLD.product_id;
        NEW.product_id = NULL;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER product_amount_check 
    AFTER UPDATE OF product_amount ON position
    FOR EACH ROW 
    EXECUTE FUNCTION check_product_amount();