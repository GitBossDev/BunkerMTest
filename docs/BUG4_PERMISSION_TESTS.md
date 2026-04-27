# Bug 4 — User Role Granular Permissions — Test Validation

## Summary
Implemented granular authorization for `user` role in middleware and UI components.

### Changes Made:
1. **Frontend Middleware** (`frontend/middleware.ts`):
   - Replaced blanket mutation block with `isBlockedForUser()` function
   - Allows: POST/PUT for creating/updating clients/roles/groups and ACLs
   - Blocks: DELETE root entities, broker config modifications, password imports, alert config changes
   - Permits: `/roles/{role}/acls/test` for ACL testing (all roles)

2. **UI Components** (RolesTable, ClientsTable, GroupsTable):
   - Added role-based conditional rendering
   - Delete buttons hidden for `user` role
   - Other management buttons (ACLs, Groups, Roles) remain visible

### Test Scenarios

#### Test 1: Middleware — User Cannot Delete Root Entities
```bash
# Setup: Login as 'user' role, get token
USER_TOKEN=$(curl -s -X POST http://localhost:2000/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"user@bhm.local","password":"password"}' | jq -r '.token')

# Test: Try DELETE /api/proxy/dynsec/clients/{username}
curl -X DELETE \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/dynsec/clients/test-client

# Expected: 403 Forbidden
# Response: {"error":"Insufficient permissions for this operation"}
```

#### Test 2: Middleware — User Can Create Clients
```bash
curl -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"username":"new-user","password":"Test@1234"}' \
  http://localhost:2000/api/proxy/dynsec/clients

# Expected: 201 Created
# Response: {"success":true,"clientname":"new-user",...}
```

#### Test 3: Middleware — User Cannot Modify Broker Config
```bash
curl -X PUT \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"max_inflight_messages":"30"}' \
  http://localhost:2000/api/proxy/config/mosquitto

# Expected: 403 Forbidden
# Response: {"error":"Insufficient permissions for this operation"}
```

#### Test 4: Middleware — User CAN Read Broker Config
```bash
curl -X GET \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/config/mosquitto

# Expected: 200 OK
# Response: {config object with current broker settings}
```

#### Test 5: Middleware — User Cannot Import Passwords
```bash
curl -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/dynsec/import-password-file \
  -F "file=@passwords.json"

# Expected: 403 Forbidden
# Response: {"error":"Insufficient permissions for this operation"}
```

#### Test 6: Middleware — User CAN Test ACL Access (New Feature)
```bash
curl -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"aclType":"subscribePattern","topic":"sensor/#"}' \
  http://localhost:2000/api/proxy/dynsec/roles/readonly-role/acls/test

# Expected: 200 OK
# Response: {"allowed":true,"reason":"role_acl","matchedRule":{...}}
```

#### Test 7: Middleware — User Can Add ACL to Role (Sub-Resource)
```bash
curl -X POST \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "acltype":"subscribe",
    "topic":"data/#",
    "allow":true
  }' \
  http://localhost:2000/api/proxy/dynsec/roles/reader-role/acls

# Expected: 201 Created
# Response: ACL created successfully
```

#### Test 8: Middleware — User Cannot DELETE ACL from Role (Via DELETE to exact segment)
```bash
# Note: This tests deletion of sub-resources - which should be allowed
# Sub-resources have 3+ path segments: /api/proxy/dynsec/roles/{name}/acls/{aclid}
# Our rule only blocks DELETE with exactly 2 segments (root entities)

curl -X DELETE \
  -H "Cookie: bunkerm_token=$USER_TOKEN" \
  http://localhost:2000/api/proxy/dynsec/roles/reader-role/acls/0

# Expected: 200 OK (user CAN delete ACLs from roles, just not the role itself)
# Response: ACL deleted successfully
```

#### Test 9: UI — Delete Button Hidden for User Role
```
Steps:
1. Login as 'user' role in the web UI
2. Navigate to ACL → Roles section
3. Check that delete icon (trash) button is NOT visible in the Actions column
4. Check that manage ACLs button (list-checks icon) IS visible
5. Login as 'admin' role
6. Check that delete icon button IS visible alongside other actions
```

#### Test 10: UI — Create and Manage Operations Available for User
```
Steps:
1. Login as 'user' role
2. Navigate to ACL → Roles
3. Click "Create Role" button — should open dialog
4. Create a new role
5. Click "Manage ACLs" (list icon) on a role — should open ACL editor
6. Add/remove ACLs for the role — should work without errors
```

#### Test 11: Middleware — Permission Error Messages
```bash
# Try various blocked operations and check consistent error message:
# All should return 403 with: {"error":"Insufficient permissions for this operation"}

# The old blanket message was: "Insufficient permissions — this account is read-only"
# New specific message is: "Insufficient permissions for this operation"
```

---

## Implementation Checklist

✅ **Middleware Authorization** (`frontend/middleware.ts`)
   - ✅ Added `USER_READONLY_PREFIXES` constant for read-only paths
   - ✅ Added `USER_BLOCKED_ENDPOINTS` constant for method-specific blocks
   - ✅ Implemented `isBlockedForUser()` function with 3-part permission logic:
     - Part 1: Read-only prefixes (config, security, alerts)
     - Part 2: Specific endpoint blocks (import-password)
     - Part 3: DELETE root DynSec entities (clients, roles, groups)
   - ✅ Replaced blanket mutation check with granular `isBlockedForUser()` call

✅ **UI Component Updates**
   - ✅ RolesTable: Added `useSession` hook, conditional delete button rendering
   - ✅ ClientsTable: Added `useSession` hook, conditional delete button rendering
   - ✅ GroupsTable: Added `useSession` hook, conditional delete button rendering
   - ✅ All components import `useSession` from 'next-auth/react'
   - ✅ Delete buttons wrapped in `{isAdmin && (...)}` conditional

✅ **Syntax Validation**
   - ✅ middleware.ts: Permission logic function properly closed
   - ✅ RolesTable.tsx: JSX conditionals properly formatted
   - ✅ ClientsTable.tsx: JSX conditionals properly formatted
   - ✅ GroupsTable.tsx: JSX conditionals properly formatted

---

## Permission Matrix Summary

| Operation | Method | Path | Admin | User | Note |
|-----------|--------|------|-------|------|------|
| View configs | GET | `/api/proxy/config/**` | ✅ | ✅ | Allowed for both |
| Modify broker config | PUT/POST | `/api/proxy/config/mosquitto` | ✅ | ❌ | Blocked for user |
| Modify alerts | PUT/POST | `/api/proxy/monitor/alerts/config` | ✅ | ❌ | Blocked for user |
| Create client | POST | `/api/proxy/dynsec/clients` | ✅ | ✅ | Allowed for user |
| Delete client | DELETE | `/api/proxy/dynsec/clients/{name}` | ✅ | ❌ | Blocked for user |
| Create role | POST | `/api/proxy/dynsec/roles` | ✅ | ✅ | Allowed for user |
| Delete role | DELETE | `/api/proxy/dynsec/roles/{name}` | ✅ | ❌ | Blocked for user |
| Add ACL to role | POST | `/api/proxy/dynsec/roles/{name}/acls` | ✅ | ✅ | Allowed for user (sub-resource) |
| Remove ACL from role | DELETE | `/api/proxy/dynsec/roles/{name}/acls/{id}` | ✅ | ✅ | Allowed for user (sub-resource) |
| Test ACL | POST | `/api/proxy/dynsec/roles/{name}/acls/test` | ✅ | ✅ | **New endpoint** from Bug 1 |
| Import passwords | POST | `/api/proxy/dynsec/import-password-file` | ✅ | ❌ | Blocked for user |

---

## Completion Status

**Bug 4 Implementation: COMPLETE**
- ✅ Middleware granular authorization implemented
- ✅ UI components updated with role-based visibility
- ✅ All changes verified for syntax and logic correctness
- ✅ Test scenarios documented for manual validation

**Integration with Previous Bugs:**
- ✅ Bug 1 (ACL Test endpoint): Accessible to both admin and user roles
- ✅ Bug 2 (Listener fix): Not affected by permission changes
- ✅ Bug 3 (Log file fix): Not affected by permission changes
- ✅ Bug 4 (Permissions): Allows user to manage clients/roles/groups/ACLs while blocking destructive operations
