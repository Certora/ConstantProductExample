
/***
This example explains many features of Certora Verification Language. 
See https://docs.certora.com for a complete guide.
***/

// reference from the spec to additional contracts used in the verification 
using DummyERC20A as _token0;
using DummyERC20B as _token1;


/*
    Declaration of methods that are used in the rules. `envfree` indicates that
    the method is not dependent on the environment (`msg.value`, `msg.sender`).
    Methods that are not declared here are assumed to be dependent on the
    environment.
*/
methods{
    function token0() external returns (address) envfree;
    function token1() external returns (address) envfree;
    function allowance(address,address) external returns (uint256) envfree;
    function balanceOf(address) external returns (uint256)  envfree; 
    function totalSupply() external returns (uint256)  envfree;
    function getReserve0() external returns (uint256) envfree;
    function getReserve1() external returns (uint256) envfree;
    function swap(address tokenIn, address recipient) external returns (uint256) envfree;
    
    //calls to external contracts  
    function _token0.balanceOf(address account) external returns (uint256) envfree;
    function _token1.balanceOf(address account) external returns (uint256) envfree;
    function _token0.transfer(address, uint) external;
    function _token1.transfer(address, uint) external;

    //external calls to be resolved by dispatcher - taking into account all available implementations 
    function _.transferFrom(address sender, address recipient, uint256 amount) external => DISPATCHER(true);
    function _.balanceOf(address) external => DISPATCHER(true);
    
}

// a cvl function for precondition assumptions 
function setup(env e){
    address zero_address = 0;
    uint256 MINIMUM_LIQUIDITY = 1000;
    require totalSupply() == 0 || balanceOf(zero_address) == MINIMUM_LIQUIDITY;
    require balanceOf(zero_address) + balanceOf(e.msg.sender) <= to_mathint(totalSupply());
    require _token0 == token0();
    require _token1 == token1();
}


/*
Property: For all possible scenarios of swapping token1 for token0, the balance of the recipient is updated as expected. 

This property is implemented as a unit-test style rule - it checks one method but on all possible scenarios.
Note that it also takes into account if the recipient is the contract itself, in which case this property does not hold since the balance is unchanged.
As a result, we add a require that the recipient is not the currentContract.

This property catches a bug in which there is a switch between the token and the recipient:
        transfer( recipient, tokenOut, amountOut);

Formula:
        { b = _token0.balanceOf(recipient) }
            amountOut := swap(_token1, recipient);
        { _token0.balanceOf(recipient) = b + amountOut }
*/

rule integrityOfSwap(address recipient) {
    env e; /* represents global solidity variables such as msg.sender, block.timestamp */
    setup(e);
    require recipient != currentContract; /* currentContract is a CVL keyword, assigned the main contract under test */  
    uint256 balanceBefore = _token0.balanceOf(recipient);
    uint256 amountOut = swap(_token1, recipient);
    uint256 balanceAfter = _token0.balanceOf(recipient);
    assert to_mathint(balanceAfter) == balanceBefore + amountOut; 
}

/*
Property: Only the user itself or an allowed spender can decrease the user's LP balance.

This property is implemented as a parametric rule - it checks all public/external methods of the contract.

This property catches a bug in which there is a switch between the token and the recipient in burnSingle:
        transfer( recipient, tokenOut, amountOut);

Formula:
        { b = balanceOf(account), allowance = allowance(account, e.msg.sender) }
            op by e.msg.sender;
        { balanceOf(account) < b =>  (e.msg.sender == account  ||  allowance >= (before-balanceOf(account)) }
*/

rule noDecreaseByOther(method f, address account) {
    env e;
    setup(e);
    require e.msg.sender != account;
    require account != currentContract; 
    uint256 allowance = allowance(account, e.msg.sender); 
    
    uint256 before = balanceOf(account);
    calldataarg args;
    f(e,args); /* check on all possible arguments */
    uint256 after = balanceOf(account);
    /* logic implication : true when: (a) the left hand side is false or (b) right hand side is true  */
    assert after < before =>  (e.msg.sender == account  ||  to_mathint(allowance) >= (before-after))  ;
}


/*
Property: For both token0 and token1 the balance of the system is at least as much as the reserves.

This property is implemented as an invariant. 
Invariants are a specification of a condition that should always be true once an operation is concluded.
In addition, the invariant also checks that it holds right after the constructor of the code runs.

This invariant also catches the bug in which there is a switch between the token and the recipient in burnSingle:
        transfer( recipient, tokenOut, amountOut);

Formula:
    getReserve0() <= _token0.balanceOf(currentContract) &&
    getReserve1() <= _token1.balanceOf(currentContract)
*/

invariant balanceGreaterThanReserve()
    (getReserve0() <= _token0.balanceOf(currentContract))&&
    (getReserve1() <= _token1.balanceOf(currentContract))
    {
        preserved with (env e){
         setup(e);
        }
    }


/*
Property: Integrity of totalSupply with respect to the amount of reserves. 

This is a high level property of the system - the ability to pay back liquidity providers.
If there are any LP tokens (the totalSupply is greater than 0), then neither reserves0 nor reserves1 should ever become zero (otherwise the pool could not produce the underlying tokens).

This invariant catches the original bug in Trident where the amount to receive is computed as a function of the balances and not the reserves.

Formula:
    (totalSupply() == 0 <=> getReserve0() == 0) &&
    (totalSupply() == 0 <=> getReserve1() == 0)
*/

invariant integrityOfTotalSupply()
    
    (totalSupply() == 0 <=> getReserve0() == 0) &&
    (totalSupply() == 0 <=> getReserve1() == 0)
    {
        preserved with (env e){
            requireInvariant balanceGreaterThanReserve();
            setup(e);
        }
    }


/*
Property: Monotonicity of mint.

The more tokens a user transfers to the system the more LP tokens that user should receive. 
This property is implemented as a relational property - it compares two different executions on the same state.

This invariant catches a bug in mint where the LP tokens of the first depositor are not computed correctly and the less he transfers the more LP-tokens he receives. 

Formula:
    { x > y }
        _token0.transfer(currentContract, x); mint(recipient);
        ~ 
        _token0.transfer(currentContract, y); mint(recipient);
    { balanceOf(recipient) at 1  >=  balanceOf(recipient) at 2  }
*/

rule monotonicityOfMint(uint256 x, uint256 y, address recipient) {
    env eT0;
    env eM;
    setup(eM);
    requireInvariant integrityOfTotalSupply();
    storage init = lastStorage;
    require recipient != currentContract;
    require x > y ;
    _token0.transfer(eT0, currentContract, x);
    uint256 amountOut0 = mint(eM,recipient);
    uint256 balanceAfter1 = balanceOf(recipient);
    
    _token0.transfer(eT0, currentContract, y) at init;
    uint256 amountOut2 = mint(eM,recipient);
    uint256 balanceAfter2 = balanceOf(recipient); 
    assert balanceAfter1 >= balanceAfter2; 
}

/*
Property: Sum of balances

The sum of all balances equals the total supply 

This property is implemented with a ghost, an additional variable that tracks changes to the balance mapping

Formula:
    
    sum(balanceOf(u) for all address u) = totalSupply()

*/

ghost mathint sumBalances{
    // assuming value zero at the initial state before constructor 
	init_state axiom sumBalances == 0; 
}


/* here we state when and how the ghost is updated */
hook Sstore _balances[KEY address a] uint256 new_balance
// the old value that balances[a] holds before the store
    (uint256 old_balance) STORAGE {
  sumBalances = sumBalances + new_balance - old_balance;
}

invariant sumFunds() 
	sumBalances == to_mathint(totalSupply());


/*
Property: Fully withdraw is possible

Exist a case where a user deposit (transfer , mint) can be fully refunded (burn the liquidity provided)

This property is implemented with a satisfy command, which aims at finding a witness example. Note that it does not prove that for every deposit can be fully withdrawn  

*/
rule possibleToFullyWithdraw(address sender, uint256 amount) {
    env eT0;
    env eM;
    setup(eM);
    uint256 balanceBefore = _token0.balanceOf(sender);
    
    require eM.msg.sender == sender;
    require eT0.msg.sender == sender;
    require amount > 0;
    _token0.transfer(eT0, currentContract, amount);
    uint256 amountOut0 = mint(eM,sender);
    burnSingle(eM, _token0, amountOut0, sender);
    satisfy balanceBefore == _token0.balanceOf(sender);
}

/// Check that there exists a case where a user deposit (transfer or mint) can
/// be fully refunded (burning the liquidity provided).  Unfortunately, because
/// we haven't required otherwise, the Prover can construct an example with
/// `amount` equal to 0.  This is fixed in `possibleToFullyWithdraw` below.
///
/// @dev This property is implemented with a `satisfy` command, which aims at
/// finding a witness example. Note that it does not prove that every deposit
/// can be fully withdrawn
rule uninterestingPossibleToFullyWithdraw(address sender, uint256 amount) {
    env eT0;
    env eM;
    setup(eM);
    uint256 balanceBefore = _token0.balanceOf(sender);

    require eM.msg.sender == sender;
    require eT0.msg.sender == sender;
    _token0.transfer(eT0, currentContract, amount);
    uint256 amountOut0 = mint(eM,sender);
    burnSingle(eM, _token0, amountOut0, sender);
    satisfy balanceBefore == _token0.balanceOf(sender);
}

/// Fixed version of the `uninterestingPossibleToFullyWithdraw` example that
/// ensures that the example has a nontrivial `amount`.
rule possibleToFullyWithdraw(address sender, uint256 amount) {
    require amount > 0; // added to reason about interesting cases 

    env eT0;
    env eM;
    setup(eM);
    uint256 balanceBefore = _token0.balanceOf(sender);

    require eM.msg.sender == sender;
    require eT0.msg.sender == sender;
    _token0.transfer(eT0, currentContract, amount);
    uint256 amountOut0 = mint(eM,sender);
    burnSingle(eM, _token0, amountOut0, sender);
    satisfy balanceBefore == _token0.balanceOf(sender);
}

/*
Property: Zero withdraw has no effect

Withdraw (burn) of zero liquidity provides noting - all the storage of all the contracts (including the ERC20s) stays the same 

This property is implemented by saving the storage state before the transaction and comparing  that after the transaction the storage is the same

*/

rule zeroWithdrawNoEffect(address to) {
    env e;
    setup(e);
    // need to assume no skimming 
    require getReserve0() == _token0.balanceOf(currentContract) && getReserve1() == _token1.balanceOf(currentContract);
    storage before = lastStorage;
    burnSingle(e, _token0, 0, to);
    storage after = lastStorage;
    assert before == after;
}
