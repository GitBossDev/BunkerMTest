#!/bin/bash
# Quick validation of the next-auth version fix

echo "==== Validating next-auth version fix ===="
echo ""

cd bunkerm-source/frontend

echo "1. Checking package.json next-auth version..."
grep '"next-auth"' package.json
echo ""

echo "2. Clearing npm cache..."
npm cache clean --force > /dev/null 2>&1
echo "   ✓ Cache cleared"
echo ""

echo "3. Running npm ci to fetch dependencies..."
npm ci --prefer-offline --no-audit 2>&1 | tail -20
echo ""

echo "4. Checking if next-auth was installed..."
if [ -d "node_modules/next-auth" ]; then
  echo "   ✓ next-auth installed successfully"
  npm ls next-auth
else
  echo "   ✗ next-auth NOT found in node_modules"
  exit 1
fi
echo ""

echo "5. Validating TypeScript syntax..."
npx tsc --noEmit 2>&1 | head -20
echo ""

echo "==== Validation Complete ===="
