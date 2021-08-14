# Contributing Code

You've made changes to the codebase and now you want to share them
with the rest of the team! Here are the best practices for the process.

## The process

Whenever you wish to make a change to the switch code, use the following
procedure.

1. Create a new git branch.

2. Make your changes on that branch.

3. Once your changes are final and ready to be added to the switch main
branch, create a pull request on Github.
   
4. If your change is a breaking change add it to `REAM Model Changelog.md`.
   
5. Get someone to review and then merge your changes on Github.

For more information read [this excellent guide](https://guides.github.com/introduction/flow/) (5 min read).

## Testing your changes

Before contributing code, it's important to test your changes.

The most important is to run `switch compare` between the previous stable version and the new version
to ensure there's no unexpected change. Beyond that, switch doesn't have an 
excellent way to test its code so you mainly need to be careful and compare 
the results before and after your changes to see if your change is working 
as expected. 

Switch does however have a small test suite which you can run by calling
`python run_tests.py` in the switch root directory. This will ensure
that the results of the examples in `examples/` haven't changed. This is
useful if you're making a change to the switch code that you believe should 
not change the final results (e.g. a refactor). If your changes are
supposed to alter the results of the examples, you'll need
to follow the instructions that appear on screen to suppress the errors
produced by `python run_tests.py`.

## Important notes

- If your change is modifying the database, make sure you've read [`Database.md`](./Database.md).