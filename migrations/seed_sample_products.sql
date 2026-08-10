INSERT INTO products (name, description, category, price, image)
SELECT 'Fresh Apples', 'Crisp and naturally sweet red apples, sold as a 1 kg pack.', 'Groceries', 149.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Fresh Apples');

INSERT INTO products (name, description, category, price, image)
SELECT 'Whole Milk', 'Fresh whole milk for breakfast, tea, coffee, and everyday cooking.', 'Dairy', 68.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Whole Milk');

INSERT INTO products (name, description, category, price, image)
SELECT 'Brown Bread', 'Soft whole-wheat bread with a wholesome texture and fresh taste.', 'Bakery', 55.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Brown Bread');

INSERT INTO products (name, description, category, price, image)
SELECT 'Breakfast Cereal', 'Crunchy multigrain cereal for a quick and satisfying breakfast.', 'Breakfast', 225.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Breakfast Cereal');

INSERT INTO products (name, description, category, price, image)
SELECT 'Fresh Carrots', 'Farm-fresh carrots, ideal for salads, curries, and healthy snacks.', 'Vegetables', 48.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Fresh Carrots');

INSERT INTO products (name, description, category, price, image)
SELECT 'Orange Juice', 'Refreshing orange juice with a bright citrus taste.', 'Beverages', 120.00, 'smartcart-groceries.png'
WHERE NOT EXISTS (SELECT 1 FROM products WHERE name = 'Orange Juice');
