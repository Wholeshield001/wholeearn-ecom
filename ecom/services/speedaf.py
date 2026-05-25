import os
import requests
import hashlib
import time
import json
from django.conf import settings
import logging

logger = logging.getLogger(__name__)

class SpeedAFClient:
    """
    Service client for integrating with the SpeedAF Express Logistics API.
    Handles authentication, signature generation, and endpoint communication.
    """
    def __init__(self):
        self.app_code = settings.SPEEDAF_APP_CODE
        self.app_key = settings.SPEEDAF_APP_KEY
        self.customer_code = settings.SPEEDAF_CUSTOMER_CODE
        self.base_url = settings.SPEEDAF_BASE_URL.rstrip('/')
        self.product_code = settings.SPEEDAF_PRODUCT_CODE or "1"
        self.subject_code = settings.SPEEDAF_SUBJECT_CODE or "101"
        self.send_province_code = settings.SPEEDAF_SEND_PROVINCE_CODE
        self.send_city_code = settings.SPEEDAF_SEND_CITY_CODE
        self.send_address = settings.SPEEDAF_SEND_ADDRESS
        self.platform_source = settings.SPEEDAF_PLATFORM_SOURCE or "csp"
        self.delivery_type = settings.SPEEDAF_DELIVERY_TYPE or "DE01"
        self.parcel_type = settings.SPEEDAF_PARCEL_TYPE or "PT01"
        self.pay_method = settings.SPEEDAF_PAY_METHOD or "PA01"
        self.ship_type = settings.SPEEDAF_SHIP_TYPE or "ST01"
        self.transport_type = settings.SPEEDAF_TRANSPORT_TYPE or "TT02"
        self.tax_method = settings.SPEEDAF_TAX_METHOD
        self._normalize_sender_location()

    def _normalize_sender_location(self):
        """Keep sender province/city codes consistent for quoting and order creation."""
        province_map, _, city_to_province_map = self._load_areas_lookup()
        if not self.send_city_code or not self.send_province_code:
            return

        expected_province = city_to_province_map.get(self.send_city_code)
        if not expected_province:
            logger.warning(
                "SpeedAF sender city code not found in areas map | sendCityCode=%s sendProvinceCode=%s",
                self.send_city_code,
                self.send_province_code,
            )
            return

        if expected_province != self.send_province_code:
            logger.warning(
                "SpeedAF sender location mismatch detected. Auto-correcting province | sendCityCode=%s mappedProvince=%s oldProvince=%s",
                self.send_city_code,
                expected_province,
                self.send_province_code,
            )
            self.send_province_code = expected_province
            logger.info(
                "SpeedAF sender location normalized | sendProvinceCode=%s sendProvinceName=%s sendCityCode=%s",
                self.send_province_code,
                province_map.get(self.send_province_code, self.send_province_code),
                self.send_city_code,
            )
        
    def _generate_signature(self, payload_dict):
        """
        SpeedAF uses a custom signature/hash for requests.
        Typically: md5(timestamp + appKey + data)
        """
        import time, json, hashlib
        timestamp = str(int(time.time() * 1000))
        # Ensure JSON keys are sorted alphabetically for deterministic hashing
        payload_str = json.dumps(payload_dict, separators=(',', ':'), ensure_ascii=False, sort_keys=True) if payload_dict else '""'
        raw_str = f"{timestamp}{self.app_key}{payload_str}"
        signature = hashlib.md5(raw_str.encode('utf-8')).hexdigest().lower()
        return signature, timestamp, payload_str
        
    def _post(self, endpoint, payload_data):
        """Helper to manage POST requests and standard error handling."""
        if not self.app_code or not self.app_key:
            logger.error("SpeedAF credentials missing. Aborting API call.")
            return {"success": False, "error": {"message": "SpeedAF credentials missing"}}

        if self.customer_code and self.app_code == self.customer_code:
            logger.warning(
                "SpeedAF config warning: appCode equals customerCode (%s). appCode is usually a separate credential from SpeedAF and may cause invalid appCode errors.",
                self.app_code,
            )
            
        signature, timestamp, payload_str = self._generate_signature(payload_data)
        url = f"{self.base_url}/{endpoint.lstrip('/')}?appCode={self.app_code}&timestamp={timestamp}"
        
        # Serialize the network payload. Bypassing SpeedAF's object map re-serialization by passing data as a primitive string.
        import json
        request_body_dict = {
            "data": payload_str,
            "sign": signature
        }
        request_body_str = json.dumps(request_body_dict, separators=(',', ':'), ensure_ascii=False)
        
        headers = {'Content-Type': 'application/json; charset=utf-8'}
        
        try:
            response = requests.post(url, data=request_body_str.encode('utf-8'), headers=headers, timeout=20)
            response.raise_for_status()
            try:
                data = response.json()
            except ValueError:
                logger.error(
                    "SpeedAF non-JSON response | endpoint=%s status=%s body=%s",
                    endpoint,
                    response.status_code,
                    response.text[:1000],
                )
                return {"success": False, "error": {"message": "SpeedAF returned non-JSON response"}, "raw": response.text[:1000]}

            if isinstance(data, dict) and not data.get("success"):
                err = data.get("error") or {}
                logger.error(
                    "SpeedAF API error | url=%s endpoint=%s code=%s message=%s payload=%s",
                    url,
                    endpoint,
                    err.get("code"),
                    err.get("message"),
                    payload_data,
                )
            return data
        except requests.RequestException as e:
            status = getattr(getattr(e, "response", None), "status_code", None)
            body = getattr(getattr(e, "response", None), "text", "")
            logger.error(
                "SpeedAF request failed | endpoint=%s status=%s error=%s payload=%s body=%s",
                endpoint,
                status,
                str(e),
                payload_data,
                body[:1000] if body else None,
            )
            return {"success": False, "error": {"message": str(e), "status": status, "body": body[:1000] if body else None}}

    def calculate_shipping_rate(self, city, state, weight=1.0):
        """
        Fetch a dynamic price quote from SpeedAF based on destination and package weight.
        """
        import time
        payload = {
            "customerCode": self.customer_code,
            "deliveryCityCode": city,
            "deliveryProvinceCode": state,
            "deliveryCountryCode": "NG",
            "sendCountryCode": "NG",
            "sendProvinceCode": self.send_province_code,
            "sendCityCode": self.send_city_code,
            "pickedTime": int(time.time() * 1000),
            "productCode": self.product_code,
            "subjectCode": self.subject_code,
            "weight": str(weight)
        }
        
        data = self._post('/open-api/fee/getFee', payload)

        if data and data.get('success'):
            fees = data.get('data', [])
            if fees and len(fees) > 0:
                if fees[0].get('fee') is None:
                    logger.error("SpeedAF fee quote missing fee field | response=%s", data)
                    return None
                quoted_fee = float(fees[0].get('fee'))
                logger.info(
                    "SpeedAF fee quote success | sendProvinceCode=%s sendCityCode=%s deliveryProvinceCode=%s deliveryCityCode=%s weight=%s fee=%s raw=%s",
                    self.send_province_code,
                    self.send_city_code,
                    state,
                    city,
                    weight,
                    quoted_fee,
                    fees[0],
                )
                return quoted_fee
            
        err = (data or {}).get('error') or {}
        logger.error(
            "Calculate shipping rate failed | deliveryProvinceCode=%s deliveryCityCode=%s weight=%s code=%s message=%s response=%s",
            state,
            city,
            weight,
            err.get('code'),
            err.get('message'),
            data,
        )
        if err.get('code') == '1100024':
            logger.error(
                "SpeedAF quote offer not matched. Verify account route pricing setup for sender(%s/%s) -> destination(%s/%s).",
                self.send_province_code,
                self.send_city_code,
                state,
                city,
            )
        return None

    def _load_areas_lookup(self):
        """Build code->name lookup dicts from the SpeedAF areas JSON file."""
        try:
            areas_path = os.path.join(os.path.dirname(__file__), 'speedaf_areas.json')
            with open(areas_path, 'r') as f:
                areas = json.load(f)
            province_map = {}
            city_map = {}
            city_to_province_map = {}
            for state in areas:
                province_map[state['code']] = state['name']
                for city in state.get('cities', []):
                    city_map[city['code']] = city['name']
                    city_to_province_map[city['code']] = state['code']
            return province_map, city_map, city_to_province_map
        except Exception as e:
            logger.warning("Failed to load SpeedAF areas lookup: %s", e)
            return {}, {}, {}

    def create_shipping_order(self, order):
        """
        Convert a Django Order into a SpeedAF-compliant JSON payload and push it.
        """
        items = list(order.items.select_related('product'))
        total_qty = sum(item.quantity for item in items) or 1
        total_weight = 0.0
        for item in items:
            unit_weight = float(getattr(item.product, 'weight_kg', 1.0) or 1.0)
            total_weight += unit_weight * item.quantity
        total_weight = total_weight or 1.0

        province_map, city_map, _ = self._load_areas_lookup()

        accept_province_name = province_map.get(order.shipping_state, order.shipping_state)
        accept_city_name = city_map.get(order.shipping_city, order.shipping_city)
        send_province_name = province_map.get(self.send_province_code, "Lagos")
        send_city_name = city_map.get(self.send_city_code, "Lagos")

        base_payload = {
            "customerCode": self.customer_code,
            "customOrderNo": str(order.id),

            # Sender Information (Warehouse/Store)
            "sendName": "WholeEarn Store",
            "sendPhone": "08000000000",
            "sendMobile": "08000000000",
            "sendProvinceCode": self.send_province_code,
            "sendProvinceName": send_province_name,
            "sendCityCode": self.send_city_code,
            "sendCityName": send_city_name,
            "sendDistrictName": send_city_name,
            "sendAddress": self.send_address,
            "sendCountryCode": "NG",

            # Receiver Information
            "acceptName": f"{order.user.first_name} {order.user.last_name}".strip() or "Customer",
            "acceptPhone": order.shipping_phone,
            "acceptMobile": order.shipping_phone,
            "acceptProvinceCode": order.shipping_state,
            "acceptProvinceName": accept_province_name,
            "acceptCityCode": order.shipping_city,
            "acceptCityName": accept_city_name,
            "acceptDistrictName": accept_city_name,
            "acceptAddress": order.shipping_address,
            "acceptCountryCode": "NG",

            "piece": total_qty,
            "goodsQTY": total_qty,
            "goodsWeight": total_weight,
            "parcelWeight": total_weight,
            "parcelCurrencyType": "NGN",
            "codFee": 0,
            "shippingFee": 0,
            "currencyType": "NGN",
            "platformSource": self.platform_source,
            "deliveryType": self.delivery_type,
            "parcelType": self.parcel_type,
            "payMethod": self.pay_method,
            "transportType": self.transport_type,
            "pickUpAging": 0,
            "itemList": [{
                "sku": str(order.id)[:50],
                "goodsName": "E-commerce order",
                "goodsNameDialect": "电商订单",
                "goodsType": "IT01",
                "goodsQTY": total_qty,
                "goodsWeight": total_weight,
                "goodsValue": float(order.total_amount),
                "currencyType": "NGN",
                "blInsure": 0,
                "battery": 0,
            }]
        }

        # ST01 = Standard express: taxMethod must NOT be passed (per SpeedAF docs)
        # ST02 = Speedaf eParcel: taxMethod required (DDP or DDU)
        attempts = [
            (self.ship_type, self.tax_method),
            (self.ship_type, ""),
            ("ST02", "DDU"),
            ("ST02", "DDP"),
        ]

        seen = set()
        data = None
        for ship_type, tax_method in attempts:
            key = (ship_type or "", tax_method or "")
            if key in seen:
                continue
            seen.add(key)

            payload = dict(base_payload)
            payload["shipType"] = ship_type or self.ship_type
            if tax_method:
                payload["taxMethod"] = tax_method

            data = self._post('/open-api/express/order/createOrder', payload)
            if not isinstance(data, dict):
                logger.error(f"Unexpected SpeedAF createOrder response type: {type(data)} payload={payload} response={data}")
                break

            if data.get("success"):

                response_body = data.get("data") or data.get("responseBody") or {}

                if not isinstance(response_body, dict):
                    response_body = {}

                waybill_code = (
                    response_body.get("waybillCode")
                    or response_body.get("mailNo")
                    or response_body.get("trackingNo")
                    or response_body.get("orderNo")
                    or ""
                )

                logger.info(
                    "SpeedAF createOrder success | order_id=%s shipType=%s taxMethod=%s waybill=%s raw=%s",
                    order.id,
                    payload.get("shipType"),
                    payload.get("taxMethod", "(none)"),
                    waybill_code,
                    data
                )

                # return str(order.id), waybill_code
                break

            error_message = str(((data.get("error") or {}).get("message") or "")).lower()
            logger.warning(
                "SpeedAF createOrder attempt failed | order_id=%s shipType=%s taxMethod=%s response=%s",
                order.id,
                payload.get('shipType'),
                payload.get('taxMethod'),
                data,
            )
            # Continue retrying only for known route/config mismatch errors.
            if not any(
                msg in error_message
                for msg in [
                    "tax method does not match shiptype",
                    "tax method does not match country",
                    "ship type error",
                ]
            ):
                break
        
        if isinstance(data, dict) and data.get('success'):
            response_body = data.get('data')
            if isinstance(response_body, str):
                try:
                    response_body = json.loads(response_body)
                except Exception:
                    logger.error(f"SpeedAF createOrder data string is not valid JSON: {response_body}")
                    return None, None
            if not isinstance(response_body, dict):
                logger.error(f"SpeedAF createOrder returned non-object data field: {response_body}")
                return None, None
            speedaf_order_id = response_body.get('customerOrderNo')
            waybill_number = response_body.get('billCode')
            return speedaf_order_id, waybill_number
            
        logger.error(f"Failed to create SpeedAF order: {data}")
        return None, None

    def track_shipment(self, tracking_number):
        """
        Fetch real-time tracking status using waybill number.
        API expects mailNoList (array); returns list of {mailNo, tracks:[...]}.
        Returns the tracks list for the requested waybill, or None on failure.
        """
        payload = {
            "mailNoList": [tracking_number]
        }

        data = self._post('/open-api/express/track/query', payload)

        logger.info(
            "SpeedAF track_shipment RAW RESPONSE | tracking=%s response=%s",
            tracking_number,
            json.dumps(data, ensure_ascii=False) if data else "None",
        )

        if data and data.get('success'):
            results = data.get('data') or []
            # Speedaf returns data as a JSON-encoded string — parse it if needed
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except (ValueError, TypeError):
                    results = []
            if isinstance(results, list) and results:
                entry = results[0]
                tracks = entry.get('tracks') or []
                logger.info(
                    "SpeedAF track_shipment PARSED TRACKS | tracking=%s entry_keys=%s track_count=%d latest=%s",
                    tracking_number,
                    list(entry.keys()),
                    len(tracks),
                    json.dumps(tracks[0], ensure_ascii=False) if tracks else "none",
                )
                return tracks
            logger.warning(
                "SpeedAF track_shipment: success=True but empty results | tracking=%s data=%s",
                tracking_number,
                json.dumps(results, ensure_ascii=False),
            )
            return []

        logger.error(
            "SpeedAF track_shipment FAILED | tracking=%s success=%s error=%s",
            tracking_number,
            data.get('success') if data else None,
            (data.get('error') or {}) if data else "no data",
        )
        return None

    def get_waybill_label(self, tracking_number):
        """
        Retrieve the PDF label URL for printing.
        """
        payload = {
            "waybillNoList": [tracking_number],
            "labelType": 2,
            "withLogo": True
        }
        
        data = self._post('/open-api/express/order/print', payload)

        if data and data.get('success'):
            return data.get('data', {}).get('url')
            
        return None
