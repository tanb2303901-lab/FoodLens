"""Shared inference/evaluation rule for overlapping specific/parent foods."""


def keep_specific_foods(boxes,classes,scores):
    """Prefer a credible grilled chicken/salmon box over its matching parent.

    Non-parent legacy foods are retained. Nested ingredients of a substantially
    different size are not silently treated as the same physical object.
    """
    kept=[]
    parents={69:{50,53},70:{17}}
    def area(b):return max(0,b[2]-b[0])*max(0,b[3]-b[1])
    for i,(box,c,score) in enumerate(zip(boxes,classes,scores)):
        if int(c) not in {17,50,53}:
            kept.append(i);continue
        suppress=False
        for j,(child,child_c,child_score) in enumerate(zip(boxes,classes,scores)):
            if c not in parents.get(int(child_c),set()) or child_score<max(.25,score*.8):continue
            intersection=max(0,min(box[2],child[2])-max(box[0],child[0]))*max(0,min(box[3],child[3])-max(box[1],child[1]))
            a,b=area(box),area(child);union=a+b-intersection
            if union>0 and intersection/union>=.5:
                suppress=True;break
        if not suppress:kept.append(i)
    return kept
