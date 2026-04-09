from tools.icloud_photo_sync.photos_bridge import PhotosResourceDescriptor
from tools.icloud_photo_sync.runtime import select_primary_media_resources


def test_select_primary_media_resources_prefers_original_over_fullsize_render_and_skips_sidecars() -> None:
    resources = [
        PhotosResourceDescriptor(
            asset_local_identifier="asset-1/L0/001",
            asset_uuid="asset-1",
            media_type=1,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=0,
            resource_type=1,
            original_filename="IMG_0001.HEIC",
            uniform_type_identifier="public.heic",
            file_size=100,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-1/L0/001",
            asset_uuid="asset-1",
            media_type=1,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=1,
            resource_type=7,
            original_filename="Adjustments.plist",
            uniform_type_identifier="com.apple.property-list",
            file_size=10,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-1/L0/001",
            asset_uuid="asset-1",
            media_type=1,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=2,
            resource_type=16,
            original_filename="IMG_0001O.aae",
            uniform_type_identifier="com.apple.photos.apple-adjustment-envelope",
            file_size=10,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-1/L0/001",
            asset_uuid="asset-1",
            media_type=1,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=3,
            resource_type=5,
            original_filename="FullSizeRender.heic",
            uniform_type_identifier="public.heic",
            file_size=90,
        ),
    ]

    selected = select_primary_media_resources(resources)
    assert [(item.resource_type, item.original_filename) for item in selected] == [
        (1, "IMG_0001.HEIC")
    ]


def test_select_primary_media_resources_keeps_live_photo_still_and_paired_video() -> None:
    resources = [
        PhotosResourceDescriptor(
            asset_local_identifier="asset-2/L0/001",
            asset_uuid="asset-2",
            media_type=1,
            media_subtypes=520,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=0,
            resource_type=1,
            original_filename="IMG_0002.HEIC",
            uniform_type_identifier="public.heic",
            file_size=100,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-2/L0/001",
            asset_uuid="asset-2",
            media_type=1,
            media_subtypes=520,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=1,
            resource_type=9,
            original_filename="IMG_0002.MOV",
            uniform_type_identifier="com.apple.quicktime-movie",
            file_size=200,
        ),
    ]

    selected = select_primary_media_resources(resources)
    assert [(item.resource_type, item.original_filename) for item in selected] == [
        (1, "IMG_0002.HEIC"),
        (9, "IMG_0002.MOV"),
    ]


def test_select_primary_media_resources_for_video_asset_prefers_video_not_rendered_jpeg() -> None:
    resources = [
        PhotosResourceDescriptor(
            asset_local_identifier="asset-3/L0/001",
            asset_uuid="asset-3",
            media_type=2,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=0,
            resource_type=2,
            original_filename="DJI_0001.MP4",
            uniform_type_identifier="public.mpeg-4",
            file_size=500,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-3/L0/001",
            asset_uuid="asset-3",
            media_type=2,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=1,
            resource_type=7,
            original_filename="Adjustments.plist",
            uniform_type_identifier="com.apple.property-list",
            file_size=10,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-3/L0/001",
            asset_uuid="asset-3",
            media_type=2,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=2,
            resource_type=5,
            original_filename="FullSizeRender.jpeg",
            uniform_type_identifier="public.jpeg",
            file_size=20,
        ),
        PhotosResourceDescriptor(
            asset_local_identifier="asset-3/L0/001",
            asset_uuid="asset-3",
            media_type=2,
            media_subtypes=0,
            creation_date="2024-01-01T00:00:00+08:00",
            modification_date=None,
            resource_index=3,
            resource_type=6,
            original_filename="FullSizeRender.mov",
            uniform_type_identifier="com.apple.quicktime-movie",
            file_size=250,
        ),
    ]

    selected = select_primary_media_resources(resources)
    assert [(item.resource_type, item.original_filename) for item in selected] == [
        (2, "DJI_0001.MP4")
    ]
