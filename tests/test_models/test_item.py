"""
Tests for ItemTemplate and UserItem models.
"""
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.item import ItemTemplate, UserItem


class TestItemModel:
    def test_item_template_creation(self, db_session):
        template = ItemTemplate(
            name="Coffee",
            description="Boosts focus",
            item_type="consumable",
            rarity="common",
            effect={"focus_boost": 10},
            duration_days=7,
            is_consumable=True,
            effect_duration_minutes=60,
            category="food_drink",
        )
        db_session.add(template)
        db_session.commit()

        assert template.id is not None
        assert len(template.id) == 36
        assert template.name == "Coffee"
        assert template.item_type == "consumable"
        assert template.rarity == "common"
        assert template.effect["focus_boost"] == 10
        assert template.category == "food_drink"

    def test_item_template_defaults(self, db_session):
        template = ItemTemplate(
            name="Notebook",
            description="Plain notebook",
            item_type="collectible",
            rarity="common",
        )
        db_session.add(template)
        db_session.commit()

        assert template.effect == {}
        assert template.is_consumable is True
        assert template.item_metadata == {}

    def test_item_template_name_unique(self, db_session):
        template1 = ItemTemplate(
            name="Unique Item",
            description="One",
            item_type="consumable",
            rarity="common",
        )
        template2 = ItemTemplate(
            name="Unique Item",
            description="Two",
            item_type="consumable",
            rarity="common",
        )
        db_session.add(template1)
        db_session.commit()

        db_session.add(template2)
        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_user_item_creation(self, db_session, sample_user):
        template = ItemTemplate(
            name="Energy Drink",
            description="Boosts energy",
            item_type="consumable",
            rarity="uncommon",
        )
        db_session.add(template)
        db_session.commit()

        user_item = UserItem(
            user_id=sample_user.id,
            template_id=template.id,
            source="quest_reward",
            source_id="quest-123",
        )
        db_session.add(user_item)
        db_session.commit()

        assert user_item.id is not None
        assert user_item.user_id == sample_user.id
        assert user_item.template_id == template.id
        assert user_item.is_equipped is False
        assert user_item.is_consumed is False
        assert user_item.item_metadata == {}

    def test_user_item_template_relationship(self, db_session, sample_user):
        template = ItemTemplate(
            name="Badge",
            description="Achievement",
            item_type="collectible",
            rarity="rare",
        )
        db_session.add(template)
        db_session.commit()

        user_item = UserItem(user_id=sample_user.id, template_id=template.id)
        db_session.add(user_item)
        db_session.commit()
        db_session.refresh(user_item)
        db_session.refresh(template)

        assert user_item.template is not None
        assert user_item.template.id == template.id
        assert user_item in template.user_items
        assert user_item.user is not None
        assert user_item.user.id == sample_user.id

    def test_user_item_expiration_logic(self, db_session, sample_user):
        template = ItemTemplate(
            name="Timed Buff",
            description="Expires soon",
            item_type="consumable",
            rarity="common",
        )
        db_session.add(template)
        db_session.commit()

        expired_at = datetime.utcnow() - timedelta(days=1)
        user_item = UserItem(
            user_id=sample_user.id,
            template_id=template.id,
            expires_at=expired_at,
        )
        db_session.add(user_item)
        db_session.commit()

        assert user_item.expires_at < datetime.utcnow()

    def test_user_item_consumption_logic(self, db_session, sample_user):
        template = ItemTemplate(
            name="Potion",
            description="Heals",
            item_type="consumable",
            rarity="common",
        )
        db_session.add(template)
        db_session.commit()

        consumed_at = datetime.utcnow()
        user_item = UserItem(
            user_id=sample_user.id,
            template_id=template.id,
            is_consumed=True,
            consumed_at=consumed_at,
        )
        db_session.add(user_item)
        db_session.commit()

        assert user_item.is_consumed is True
        assert user_item.consumed_at == consumed_at

    def test_query_equipped_items(self, db_session, sample_user):
        template1 = ItemTemplate(
            name="Equipped Item",
            description="Active",
            item_type="equipment",
            rarity="rare",
        )
        template2 = ItemTemplate(
            name="Inventory Item",
            description="Inactive",
            item_type="equipment",
            rarity="common",
        )
        db_session.add_all([template1, template2])
        db_session.commit()

        item_equipped = UserItem(
            user_id=sample_user.id,
            template_id=template1.id,
            is_equipped=True,
        )
        item_inventory = UserItem(
            user_id=sample_user.id,
            template_id=template2.id,
            is_equipped=False,
        )
        db_session.add_all([item_equipped, item_inventory])
        db_session.commit()

        equipped = (
            db_session.query(UserItem)
            .filter(UserItem.user_id == sample_user.id)
            .filter(UserItem.is_equipped == True)
            .all()
        )

        assert len(equipped) == 1
        assert equipped[0].id == item_equipped.id
