from backend.app.taxonomy import keep_specific_foods


def test_specific_grilled_food_wins_only_for_its_overlapping_parent():
    boxes=[[0,0,1,1],[.05,.05,.95,.95],[0,0,1,1],[0,0,1,1]]
    assert keep_specific_foods(boxes,[50,69,25,48],[.7,.8,.9,.8])==[1,2,3]
    assert keep_specific_foods(boxes[:2],[17,70],[.7,.8])==[1]


def test_uncertain_child_separate_objects_and_nested_ingredients_keep_parent():
    assert keep_specific_foods([[0,0,1,1]]*2,[50,69],[.9,.3])==[0,1]
    assert keep_specific_foods([[0,0,.4,.4],[.6,.6,1,1]],[50,69],[.8,.9])==[0,1]
    assert keep_specific_foods([[0,0,1,1],[.1,.1,.3,.3]],[50,69],[.7,.8])==[0,1]


def test_generic_fish_or_meat_does_not_suppress_unrelated_new_food():
    assert keep_specific_foods([[0,0,1,1]]*3,[17,69,67],[.8,.9,.9])==[0,1,2]
