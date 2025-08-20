from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from pymongo import MongoClient
from rasa_sdk.events import SlotSet
import re
import unicodedata
from bson import ObjectId

# Hàm chuẩn hóa slug (không dấu, cách thành "-")
def slugify(text):
    text = unicodedata.normalize("NFD", text)
    text = text.encode("ascii", "ignore").decode("utf-8")
    text = re.sub(r"[^\w\s-]", "", text.lower())
    return text.replace(" ", "-")

# Hàm chuyển đổi ObjectId thành chuỗi trong dữ liệu MongoDB
def convert_objectid_to_str(data):
    if isinstance(data, ObjectId):
        return str(data)
    elif isinstance(data, dict):
        return {k: convert_objectid_to_str(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [convert_objectid_to_str(item) for item in data]
    return data

# Lưu cache tạm thời các sản phẩm tìm được (theo session)
cached_results: Dict[Text, List[Dict[str, Any]]] = {}

class ActionResetSearchSlots(Action):
    def name(self) -> Text:
        return "action_reset_search_slots"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:
        return [
            SlotSet("color", None),
            SlotSet("size", None),
            SlotSet("priceRange", None),
            SlotSet("matched_products", None),
            SlotSet("product_offset", None),
            SlotSet("suggested_entity", None),
            SlotSet("suggested_value", None)
        ]

class ActionSearchProducts(Action):
    def name(self) -> Text:
        return "action_search_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        # Lấy entities từ câu hỏi
        entities = tracker.latest_message.get("entities", [])
        print(f"[DEBUG] Entities extracted: {entities}")

        # Lấy slots hiện tại
        name = tracker.get_slot("name")
        size = tracker.get_slot("size")
        price_range = tracker.get_slot("priceRange")
        id_cate = tracker.get_slot("id_cate")

        # Lấy color và priceRange từ entities
        color_entity = next((e["value"] for e in entities if e["entity"] == "color"), None)
        price_entity = next((e["value"] for e in entities if e["entity"] == "priceRange"), None)

        # Ưu tiên dùng color_entity từ câu hỏi
        color = color_entity if color_entity else tracker.get_slot("color")

        # Chỉ sử dụng priceRange nếu có trong entities
        if price_range and not price_entity:
            print(f"[WARN] priceRange slot ({price_range}) không xuất hiện trong entities, bỏ qua.")
            price_range = None

        # Loại bỏ color sai nếu nó giống giá tiền
        if color and re.match(r'\d+(k|tr|m)', color.lower()):
            print(f"[WARN] Color có vẻ sai, loại bỏ: {color}")
            color = None

        # Map alias cho priceRange
        price_alias_map = {
            "500k": "500k-1m",
            "1m": "1m-2m",
            "2m": "2m-4m",
            "4m": "over-4m",
            "trên 4 triệu": "over-4m",
            "dưới 500k": "under-500k",
            "từ 500k đến 1 triệu": "500k-1m",
            "khoảng 1 triệu đến 2 triệu": "1m-2m",
            "2 triệu tới 4 triệu": "2m-4m"
        }
        if price_range in price_alias_map:
            price_range = price_alias_map[price_range]

        print(f"[DEBUG] Slot values received: {{'name': {name}, 'color': {color}, 'size': {size}, 'priceRange': {price_range}, 'id_cate': {id_cate}}}")

        client = MongoClient("mongodb://localhost:27017/")
        try:
            db = client["DB_GraduationProject"]
            collection = db["products"]

            query = {"is_active": True}
            if name:
                query["slug"] = {"$regex": slugify(name), "$options": "i"}
            if color:
                query["variants.color"] = {"$regex": re.escape(color), "$options": "i"}
            if size:
                query["variants.size"] = {"$regex": re.escape(size), "$options": "i"}
            if id_cate:
                query["category._id"] = id_cate

            print(f"[DEBUG] MongoDB query: {query}")
            products = list(collection.find(query))
            print(f"[DEBUG] Found {len(products)} products before price filtering")

            def is_in_price_range(product):
                prices = []
                for v in product.get("variants", []):
                    price = v.get("price", 0)
                    discount = v.get("discountPercent", 0)
                    discounted = int(price * (100 - discount) / 100)
                    prices.append(discounted)

                if not prices:
                    return False

                if not price_range:
                    return True

                match price_range:
                    case "under-500k":
                        return any(p < 500000 for p in prices)
                    case "500k-1m":
                        return any(500000 <= p <= 1000000 for p in prices)
                    case "1m-2m":
                        return any(1000000 <= p <= 2000000 for p in prices)
                    case "2m-4m":
                        return any(2000000 <= p <= 4000000 for p in prices)
                    case "over-4m":
                        return any(p > 4000000 for p in prices)
                    case _:
                        return True

            filtered_products = [convert_objectid_to_str(p) for p in products if is_in_price_range(p)]
            print(f"[DEBUG] Found {len(filtered_products)} products after price filtering")

            # Nếu không có sản phẩm phù hợp
            if not filtered_products:
                dispatcher.utter_message(text="Rất tiếc, mình không tìm thấy sản phẩm nào phù hợp với yêu cầu của bạn.")
                return []

            # Lưu cache cho show_more_products
            sender_id = tracker.sender_id
            cached_results[sender_id] = filtered_products

            # Render 3 sản phẩm đầu tiên
            top_products = filtered_products[:3]
            items = []
            for p in top_products:
                prices = [
                    int(v.get("price", 0) * (100 - v.get("discountPercent", 0)) / 100)
                    for v in p.get("variants", []) if v is not None
                ]
                item = {
                    "id": p.get("_id", ""),
                    "name": p.get("name", ""),
                    "category": p.get("category", {}).get("name", ""),
                    "slug": p.get("slug", ""),
                    "price": min(prices) if prices else 0,
                    "image": p.get("image", [None])[0],
                }
                items.append(item)

            dispatcher.utter_message(text=(
                f"Mình tìm thấy {len(filtered_products)} mẫu {name or 'sản phẩm'} phù hợp với yêu cầu của bạn, đây là một số sản phẩm:"
            ))
            dispatcher.utter_message(json_message={"type": "product_list", "items": items})

            # Gợi ý thêm nếu thiếu size (không gợi ý màu nếu đã có color)
            suggested_entity = None
            suggested_value = None
            if color and not size:
                suggested_entity = "size"
                suggested_value = "M"
                dispatcher.utter_message(text=f"Bạn có muốn thử tìm {name or 'sản phẩm'} với size {suggested_value} không?")
            elif not color and not size:
                suggested_entity = "color"
                suggested_value = "trắng"
                dispatcher.utter_message(text=f"Bạn có muốn thử tìm {name or 'sản phẩm'} với màu {suggested_value} không?")

            return [
                SlotSet("matched_products", filtered_products),
                SlotSet("product_offset", 0),
                SlotSet("suggested_entity", suggested_entity),
                SlotSet("suggested_value", suggested_value),
                SlotSet("color", color),
                SlotSet("size", size),
                SlotSet("priceRange", price_range),
            ]

        finally:
            client.close()

class ActionShowMoreProducts(Action):
    def name(self) -> Text:
        return "action_show_more_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        sender_id = tracker.sender_id
        remaining_products = cached_results.get(sender_id, [])[3:]

        if not remaining_products:
            dispatcher.utter_message(text="Không còn sản phẩm nào để hiển thị thêm.")
            return []

        next_items = remaining_products[:3]
        cached_results[sender_id] = remaining_products  # Cập nhật lại cache

        items = []
        for p in next_items:
            prices = [
                int(v.get("price", 0) * (100 - v.get("discountPercent", 0)) / 100)
                for v in p.get("variants", []) if v is not None
            ]
            item = {
                "id": p.get("_id", ""),
                "name": p.get("name", ""),
                "category": p.get("category", {}).get("name", ""),
                "slug": p.get("slug", ""),
                "price": min(prices) if prices else 0,
                "image": p.get("image", [None])[0],
            }
            items.append(item)

        dispatcher.utter_message(json_message={"type": "product_list", "items": items})

        if len(remaining_products) > 3:
            dispatcher.utter_message(text="Bạn có muốn xem thêm sản phẩm nữa không?")
        else:
            dispatcher.utter_message(text="Đây là tất cả sản phẩm mình tìm được nha!")
        return []

class ActionSuggestMoreProducts(Action):
    def name(self) -> Text:
        return "action_suggest_more_products"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        suggested_entity = tracker.get_slot("suggested_entity")
        suggested_value = tracker.get_slot("suggested_value")

        print(f"[INFO] Gợi ý bị từ chối: suggested_entity={suggested_entity}, value={suggested_value}")

        dispatcher.utter_message(text="Không sao, bạn có thể cung cấp thêm thông tin khác nếu muốn nhé!")
        return [
            SlotSet("suggested_entity", None),
            SlotSet("suggested_value", None)
        ]

class ActionAcceptSuggestion(Action):
    def name(self) -> Text:
        return "action_accept_suggestion"

    def run(self, dispatcher: CollectingDispatcher,
            tracker: Tracker,
            domain: Dict[Text, Any]) -> List[Dict[Text, Any]]:

        suggested_entity = tracker.get_slot("suggested_entity")
        suggested_value = tracker.get_slot("suggested_value")
        name = tracker.get_slot("name")
        color = tracker.get_slot("color")
        size = tracker.get_slot("size")
        price_range = tracker.get_slot("priceRange")
        id_cate = tracker.get_slot("id_cate")

        print(f"[INFO] Chấp nhận gợi ý: suggested_entity={suggested_entity}, value={suggested_value}")

        # Cập nhật slot tương ứng với gợi ý
        if suggested_entity == "color":
            color = suggested_value
        elif suggested_entity == "size":
            size = suggested_value

        client = MongoClient("mongodb://localhost:27017/")
        try:
            db = client["DB_GraduationProject"]
            collection = db["products"]

            query = {"is_active": True}
            if name:
                query["slug"] = {"$regex": slugify(name), "$options": "i"}
            if color:
                query["variants.color"] = {"$regex": re.escape(color), "$options": "i"}
            if size:
                query["variants.size"] = {"$regex": re.escape(size), "$options": "i"}
            if id_cate:
                query["category._id"] = id_cate

            print(f"[DEBUG] MongoDB query (accept suggestion): {query}")
            products = list(collection.find(query))
            print(f"[DEBUG] Found {len(products)} products before price filtering")

            def is_in_price_range(product):
                prices = []
                for v in product.get("variants", []):
                    price = v.get("price", 0)
                    discount = v.get("discountPercent", 0)
                    discounted = int(price * (100 - discount) / 100)
                    prices.append(discounted)

                if not prices:
                    return False

                if not price_range:
                    return True

                match price_range:
                    case "under-500k":
                        return any(p < 500000 for p in prices)
                    case "500k-1m":
                        return any(500000 <= p <= 1000000 for p in prices)
                    case "1m-2m":
                        return any(1000000 <= p <= 2000000 for p in prices)
                    case "2m-4m":
                        return any(2000000 <= p <= 4000000 for p in prices)
                    case "over-4m":
                        return any(p > 4000000 for p in prices)
                    case _:
                        return True

            filtered_products = [convert_objectid_to_str(p) for p in products if is_in_price_range(p)]
            print(f"[DEBUG] Found {len(filtered_products)} products after price filtering")

            if not filtered_products:
                dispatcher.utter_message(text="Rất tiếc, không tìm thấy sản phẩm nào với bộ lọc mới.")
                return [
                    SlotSet("suggested_entity", None),
                    SlotSet("suggested_value", None),
                    SlotSet("color", color),
                    SlotSet("size", size),
                    SlotSet("priceRange", price_range)
                ]

            # Lưu cache
            sender_id = tracker.sender_id
            cached_results[sender_id] = filtered_products

            # Render 3 sản phẩm đầu tiên
            top_products = filtered_products[:3]
            items = []
            for p in top_products:
                prices = [
                    int(v.get("price", 0) * (100 - v.get("discountPercent", 0)) / 100)
                    for v in p.get("variants", []) if v is not None
                ]
                item = {
                    "id": p.get("_id", ""),
                    "name": p.get("name", ""),
                    "category": p.get("category", {}).get("name", ""),
                    "slug": p.get("slug", ""),
                    "price": min(prices) if prices else 0,
                    "image": p.get("image", [None])[0],
                }
                items.append(item)

            dispatcher.utter_message(text=(
                f"Mình tìm thấy {len(filtered_products)} mẫu {name or 'sản phẩm'} với {suggested_entity} {suggested_value}:"
            ))
            dispatcher.utter_message(json_message={"type": "product_list", "items": items})

            return [
                SlotSet("matched_products", filtered_products),
                SlotSet("product_offset", 0),
                SlotSet("suggested_entity", None),
                SlotSet("suggested_value", None),
                SlotSet("color", color),
                SlotSet("size", size),
                SlotSet("priceRange", price_range)
            ]

        finally:
            client.close()
