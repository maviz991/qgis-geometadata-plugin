This folder contains configuration files and custom templates for geOrchestra Gateway.

## Documentation

Documentation can be found in [docs directory at root of georchestra-gateway](https://github.com/georchestra/georchestra-gateway/blob/ui_customization_doc/docs) repository.

## List of configuration files

#### `application.yaml`

Contains filters applicable to all transfers through the gateway, and general Spring settings.

**⚠️ CRITICAL - CORS Configuration ⚠️**

The `globalcors` configuration in this file **MUST remain disabled** (commented out).

**Why?**
- CORS headers are handled exclusively by the Apache reverse proxy
- Enabling Gateway CORS causes duplicate `Access-Control-Allow-*` headers
- Duplicate headers violate CORS policy and cause browser errors
- This breaks WPS requests, API mode, and cross-origin functionality

**History:**
- 2025-11-03: Correctly disabled (commit 38dfead)
- 2025-11-04: **Accidentally re-enabled** (commit 735c479) - caused regression
- 2025-11-12: Re-disabled to fix duplicate headers bug

**Documentation:**
- `docs-cdhu/infrastructure-cors.md` - Full architecture explanation
- `openspec/changes/fix-duplicate-cors-headers/` - Original fix proposal

**⛔ DO NOT re-enable without coordinating with Apache configuration ⛔**

#### `gateway.conf`

Contains access rules for all services available through the gateway.

Please see https://github.com/georchestra/georchestra-gateway/blob/main/docs/access-rules.adoc

#### `roles-mappings.yaml`

Allow to map roles returned by authentication providers to standardized geOrchestra roles.

Please see https://github.com/georchestra/georchestra-gateway/blob/main/docs/roles-mappings.adoc

####  `routes.yaml`

Contains list of routes for redirection to the correct service URL based on criterias (typically URL patterns but other criterias exists).  
Also allows to apply additional filters on this route.

Please see https://cloud.spring.io/spring-cloud-gateway/reference/html

####  `security.yaml`

Contains all settings about authentication. Please see the following documents :  
OAuth2 : https://github.com/georchestra/georchestra-gateway/blob/main/docs/authzn.adoc  
Pre-authentication : https://github.com/georchestra/georchestra-gateway/blob/main/docs/pre-authentication.adoc  

## Templates

If needed, default pages can be overriden by custom templates. This includes login, logout page, and error pages. Only existing templates will override default ones.

Please see https://github.com/georchestra/georchestra-gateway/blob/main/docs/ui-customization.adoc
