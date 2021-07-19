"""
This post-process steps was used by Martin when studying LDES.

It adds the storage data to the input files.
"""
from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process(
    name="add_storage",
    msg="Adding storage from Google Sheets",
    only_with_config=True,
    priority=1
)
def add_storage(config):
    from switch_model.tools.add_storage import main
    main(
        run_post_solve=False,  # We will run post solve automatically right afterwards
        scenario_config=config,
        change_dir=False
    )
